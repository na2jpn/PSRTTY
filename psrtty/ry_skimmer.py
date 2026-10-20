"""Streaming IQ channelization and independent RTTY decoders (receive only)."""
from dataclasses import dataclass, field
import queue
import threading
import time
import re
import numpy as np
from scipy.signal import firwin, upfirdn
from .decoder import RTTYDecoder
from .parser import CALL_RE


def dial_for_mark(hz,tx_method,mode,mark_audio):
    if tx_method=='fsk':return round(hz)
    upper=mode.upper().startswith('USB')
    return round(hz-mark_audio if upper else hz+mark_audio)


class FIRDecimator:
    """Polyphase FIR, retaining sample phase and filter memory across blocks."""
    def __init__(self, factor):
        self.factor=max(1,int(factor));self.total=0
        self.taps=firwin(32*self.factor+1, .8/self.factor) if self.factor>1 else np.array([1.])
        self.history_len=((len(self.taps)-1+self.factor-1)//self.factor+1)*self.factor
        self.history=np.zeros(self.history_len,dtype=np.complex64)

    def feed(self, data):
        data=np.asarray(data,dtype=np.complex64)
        if self.factor==1:return data
        phase=(-self.total)%self.factor;self.total+=len(data)
        full=np.concatenate((self.history,data));self.history=full[-self.history_len:]
        count=len(range(phase,len(data),self.factor))
        filtered=upfirdn(self.taps,full[phase:],down=self.factor)
        return filtered[self.history_len//self.factor:self.history_len//self.factor+count].astype(np.complex64)


@dataclass
class Channel:
    offset: float
    rate: float
    emit: object
    mark_high: bool=True
    phase: float=0.
    text: str=''
    recent: str=''
    call: str=''
    last: float=0.
    seen: float=0.
    decimator: object=field(init=False)
    decoder: object=field(init=False)

    def __post_init__(self):
        self.decimator=FIRDecimator(max(1,round(self.rate/6000)))
        rate=self.rate/self.decimator.factor
        # Shift a complex RF pair to positive audio before taking its real part.
        self.decoder=RTTYDecoder(rate,45.45,2210 if self.mark_high else 2040,
                                 2040 if self.mark_high else 2210,on_char=self.char,on_break=self.flush)
        self.decoder.sq_level=4

    def char(self,ch):
        self.last=time.monotonic()
        if ch in '\r\n':self.flush();return
        self.text=(self.text+ch)[-200:]

    def flush(self):
        text=' '.join(self.text.split());self.text=''
        if len(text.replace(' ',''))<3:return
        self.recent=(self.recent+' '+text)[-1200:]
        # A lone addressee in "JA1ABC DE JA2XYZ" is not the transmitting station.
        de=re.findall(r'\bDE\s+([A-Z0-9/]+)',text)
        candidates=[m.group() for m in CALL_RE.finditer(text)]
        chosen=next((c for c in de if CALL_RE.fullmatch(c)), '')
        if not chosen and len(set(candidates))==1:chosen=candidates[0]
        if chosen:self.call=chosen
        self.emit(self,text)

    def feed(self,iq):
        omega=2*np.pi*(2125-self.offset)/self.rate
        phase=self.phase+omega*np.arange(len(iq))
        self.phase=(self.phase+omega*len(iq))%(2*np.pi)
        audio=self.decimator.feed(iq*np.exp(1j*phase)).real
        self.decoder.feed(audio)


class SkimmerEngine:
    def __init__(self,on_text=lambda *a:None,on_spectrum=lambda *a:None,span=20000,limit=12,mark_high=True,ja_only=False):
        self.on_text=on_text;self.on_spectrum=on_spectrum;self.span=span;self.limit=limit;self.mark_high=mark_high
        self.ja_only=ja_only
        self.channels=[];self.identity=None;self.total=0;self.last_scan=0;self.psd=None;self.fft_buffer=np.empty(0,dtype=np.complex64)

    def reset(self,rate,center):
        if not 6000<=rate<=8e6 or not np.isfinite(center):raise ValueError('IQ rate/center')
        self.identity=(rate,center);self.front=FIRDecimator(max(1,int(rate//96000)))
        self.rate=rate/self.front.factor;self.center=center;self.channels=[];self.total=0;self.last_scan=0;self.psd=None
        self.fft_buffer=np.empty(0,dtype=np.complex64)

    def allowed(self,mark):
        from .ry_ja import ja_pair
        return not self.ja_only or ja_pair(mark,self.mark_high)

    def _emit(self,channel,text):
        # Tune/display the higher RF tone (normal mark), not the FFT-pair midpoint.
        mark=self.center+channel.offset+(85 if self.mark_high else -85)
        if self.allowed(mark):self.on_text(mark,channel.call,text,channel.recent)

    def feed(self,iq,rate,center,gap=False):
        if self.identity!=(rate,center) or gap:self.reset(rate,center)
        data=self.front.feed(iq)
        if not len(data):return
        self.total+=len(data);self.fft_buffer=np.concatenate((self.fft_buffer,data))
        n=min(32768,max(4096,1<<int(np.ceil(np.log2(self.rate/6)))))
        if len(self.fft_buffer)>=n:
            # One contiguous FFT per received block; bounded independent of bandwidth.
            section=self.fft_buffer[-n:];self.fft_buffer=self.fft_buffer[-n//2:]
            spectrum=np.abs(np.fft.fftshift(np.fft.fft(section*np.hanning(n))))**2
            self.psd=spectrum if self.psd is None else .8*self.psd+.2*spectrum
            freqs=np.fft.fftshift(np.fft.fftfreq(n,1/self.rate))
            if self.total-self.last_scan>=self.rate*.4:
                self.last_scan=self.total
                db=10*np.log10(self.psd+1e-18)
                mask=np.abs(freqs)<=min(self.span/2,self.rate*.4)
                self.on_spectrum(freqs[mask]+center,db[mask],center,min(self.span,self.rate*.8))
                self._scan(freqs,db)
        self.channels=[c for c in self.channels if self.allowed(self.center+c.offset+(85 if self.mark_high else -85))]
        for channel in tuple(self.channels):channel.feed(data)

    def _scan(self,freqs,db):
        now=self.total/self.rate;floor=float(np.percentile(db,40));spacing=self.rate/len(db)
        peaks=np.flatnonzero((db[1:-1]>db[:-2])&(db[1:-1]>=db[2:]))+1
        threshold=max(floor+10,float(np.max(db))-35)
        peaks=[i for i in peaks if db[i]>threshold and abs(freqs[i])<min(self.span/2-200,self.rate*.4)]
        peaks=sorted(peaks,key=lambda i:db[i],reverse=True)[:100]
        pairs=[]
        for i in peaks:
            for j in peaks:
                if 0<freqs[j]-freqs[i] and abs(freqs[j]-freqs[i]-170)<=max(12,spacing*1.5) and abs(db[i]-db[j])<20:
                    pairs.append(((freqs[i]+freqs[j])/2,min(db[i],db[j])))
        pairs.sort(key=lambda p:p[1],reverse=True)
        for offset,strength in pairs:
            if not self.allowed(self.center+offset+(85 if self.mark_high else -85)):continue
            match=next((c for c in self.channels if abs(c.offset-offset)<150),None)
            if match:match.seen=now;continue
            if len(self.channels)>=self.limit:continue
            c=Channel(float(offset),self.rate,self._emit,self.mark_high);c.seen=now
            self.channels.append(c)
        self.channels=[c for c in self.channels if now-c.seen<8]

    def add_channel(self,hz):
        """Manual RF mark selection for weak signals missing automatic detection."""
        if not self.identity or not self.allowed(hz):return
        offset=hz-self.center-(85 if self.mark_high else -85)
        if abs(offset)>min(self.span/2-200,self.rate*.4):return
        if any(abs(c.offset-offset)<150 for c in self.channels):return
        if len(self.channels)<self.limit:
            c=Channel(offset,self.rate,self._emit,self.mark_high);c.seen=self.total/self.rate+3600;self.channels.append(c)


class SkimmerWorker:
    def __init__(self,**options):
        self.engine=SkimmerEngine(**options);self.queue=queue.Queue(maxsize=8)
        self.stop_event=threading.Event();self.thread=None;self.dropped=0;self._gap=False
        self.lock=threading.Lock();self.samples=0;self.error=None

    def start(self):
        self.thread=threading.Thread(target=self._run,daemon=True,name='PSRTTY-Skimmer');self.thread.start()

    def offer(self,iq,rate,center,gap=False):
        if self.stop_event.is_set():return
        if gap:self.dropped+=1
        try:self.queue.put_nowait((np.asarray(iq,dtype=np.complex64).copy(),rate,center,gap or self._gap));self._gap=False
        except queue.Full:self.dropped+=1;self._gap=True

    def manual(self,hz):
        with self.lock:self.engine.add_channel(hz)

    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=.3)

    def _run(self):
        try:
            while not self.stop_event.is_set():
                try:item=self.queue.get(timeout=.1)
                except queue.Empty:continue
                with self.lock:self.engine.feed(*item)
                self.samples+=len(item[0])
        except Exception as e:self.error=str(e);self.stop_event.set()
