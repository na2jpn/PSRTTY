"""Streaming IQ channelization and independent RTTY decoders (receive only)."""
from dataclasses import dataclass, field
from collections import deque
import queue
import threading
import time
import re
import numpy as np
from scipy.signal import firwin, upfirdn
from scipy.fft import fft, ifft, next_fast_len
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
        self.fft_size=0;self.fft_taps=None
        self.history_len=((len(self.taps)-1+self.factor-1)//self.factor+1)*self.factor
        self.history=np.zeros(self.history_len,dtype=np.complex64)

    def feed(self, data):
        data=np.asarray(data,dtype=np.complex64)
        if self.factor==1:return data
        phase=(-self.total)%self.factor;self.total+=len(data)
        full=np.concatenate((self.history,data));self.history=full[-self.history_len:]
        count=len(range(phase,len(data),self.factor))
        if self.factor>=16 and len(data)>=4096:
            # FFT convolution avoids hundreds of multiplies for every output
            # sample at wideband input rates. Keep phase/history identical to
            # the small-block polyphase path; switching paths is safe.
            n=next_fast_len(len(full)+len(self.taps)-1)
            if n!=self.fft_size:
                self.fft_size=n;self.fft_taps=fft(self.taps.astype(np.float32),n)
            filtered=ifft(fft(full,n)*self.fft_taps)
            return filtered[self.history_len+phase:self.history_len+len(data):self.factor].astype(np.complex64)
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
        self.monitor_center=None;self.coverage=True;self.mixer_phase=0.;self.channels=[];self.identity=None;self.total=0;self.last_scan=0;self.psd=None;self.fft_buffer=np.empty(0,dtype=np.complex64)

    def reset(self,rate,center):
        if not 6000<=rate<=8e6 or not np.isfinite(center):raise ValueError('IQ rate/center')
        self.identity=(rate,center);self.front=FIRDecimator(max(1,int(rate//96000)))
        self.rate=rate/self.front.factor;self.center=self.monitor_center if self.monitor_center is not None else center;self.mixer_phase=0.;self.channels=[];self.total=0;self.last_scan=0;self.psd=None
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
        target=self.monitor_center if self.monitor_center is not None else center
        self.coverage=abs(target-center)+min(self.span/2,rate*.4)<=rate*.4
        if not self.coverage:return
        delta=center-target
        if delta:
            omega=2*np.pi*delta/rate
            iq=np.asarray(iq,dtype=np.complex64)*np.exp(1j*(self.mixer_phase+omega*np.arange(len(iq))))
            self.mixer_phase=(self.mixer_phase+omega*len(iq))%(2*np.pi)
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
                self.on_spectrum(freqs[mask]+self.center,db[mask],self.center,min(self.span,self.rate*.8))
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

    def set_monitor_center(self,hz):
        hz=None if hz is None else float(hz)
        if self.monitor_center==hz:return
        self.monitor_center=hz
        if self.identity:self.reset(*self.identity)

    def add_channel(self,hz):
        """Manual RF mark selection for weak signals missing automatic detection."""
        if not self.identity or not self.allowed(hz):return
        offset=hz-self.center-(85 if self.mark_high else -85)
        if abs(offset)>min(self.span/2-200,self.rate*.4):return
        if any(abs(c.offset-offset)<150 for c in self.channels):return
        if len(self.channels)<self.limit:
            c=Channel(offset,self.rate,self._emit,self.mark_high);c.seen=self.total/self.rate+3600;self.channels.append(c)


class SkimmerWorker:
    """Bound input by signal duration, batch tiny callbacks before DSP.

    Producer never waits for the decoder. Dropped samples are accounted for,
    and discontinuities stay on the first subsequent accepted block.
    """
    def __init__(self, buffer_seconds=.5, batch_seconds=.02, **options):
        self.engine=SkimmerEngine(**options);self.queue=queue.Queue()
        self.buffer_seconds=buffer_seconds;self.batch_seconds=batch_seconds
        self.stop_event=threading.Event();self.thread=None;self.dropped=0;self._gap=False
        self.lock=threading.Lock();self.stats_lock=threading.Lock()
        self.samples=0;self.received=0;self.lost_samples=0;self.queued_seconds=0.
        self.input_seconds=0.;self.processed_seconds=0.;self.lost_seconds=0.;self.source_lost_seconds=0.
        self.measured_sps=0.;self.rate_ratio=0.;self.rate_warning=False;self.last_rate_warning=False;self.rate_epoch=None;self.rate_start_count=0;self.rate_start_time=0.;self.rate=0;self.center=0;self.last_arrival=0.;self.error=None
        self.history=deque();self.started=time.monotonic();self.last_snapshot=None

    def start(self):
        self.thread=threading.Thread(target=self._run,daemon=True,name='PSRTTY-Skimmer');self.thread.start()

    def offer(self,iq,rate,center,gap=False):
        if self.stop_event.is_set():return
        data=np.asarray(iq,dtype=np.complex64)
        if not len(data):return
        if not 6000<=rate<=8e6 or not np.isfinite(center):raise ValueError('IQ rate/center')
        duration=len(data)/rate
        # ExtIO supplies an exact sample-position difference. A boolean source
        # discontinuity has unknown length and is counted as an event only.
        missing=int(gap) if not isinstance(gap,(bool,np.bool_)) else 0
        with self.stats_lock:
            now=time.monotonic()
            if self.rate_epoch!=rate:
                self.rate_epoch=rate;self.rate_start_time=now;self.rate_start_count=self.received
                self.measured_sps=0.;self.rate_ratio=0.;self.rate_warning=False
            self.rate=rate;self.center=center;self.last_arrival=now
            self.received+=len(data);self.input_seconds+=duration
            if gap:
                self.dropped+=1;self.lost_samples+=max(0,missing);self.lost_seconds+=max(0,missing)/rate;self.source_lost_seconds+=max(0,missing)/rate
            if self.queued_seconds+duration>self.buffer_seconds or self.queue.qsize()>=4096:
                self.dropped+=1;self.lost_samples+=len(data);self.lost_seconds+=duration;self._gap=True
                return
            self.queued_seconds+=duration
            self.queue.put_nowait((data.copy(),rate,center,bool(gap) or self._gap))
            self._gap=False

    def snapshot(self):
        """Thread-safe counters and a rolling ten-second loss fraction."""
        now=time.monotonic()
        with self.stats_lock:
            row=(now,self.received,self.samples,self.input_seconds,self.processed_seconds,self.lost_seconds,self.source_lost_seconds)
            if not self.history:self.history.append((self.started,0,0,0.,0.,0.,0.))
            baseline=self.last_snapshot or self.history[0]
            elapsed=max(.001,now-baseline[0])
            received=max(0,row[3]-baseline[3]);processed=max(0,row[4]-baseline[4]);lost=max(0,row[5]-baseline[5])
            # queue loss is already part of input_seconds; source-position loss
            # is not. Loss is bounded for display, never discarded in counters.
            self.history.append(row)
            while len(self.history)>2 and self.history[1][0]<now-10:self.history.popleft()
            first=self.history[0];total_in=row[3]-first[3];total_lost=row[5]-first[5]
            # Exact denominator is accepted+source loss+local loss, represented
            # separately below by the accounted signal duration.
            accounted=total_in+row[6]-first[6]
            recent_loss=min(100.,100*total_lost/max(accounted,1e-12)) if total_lost else 0.
            window=now-self.rate_start_time
            if self.rate and window>=5 and now-self.last_arrival<1:
                self.measured_sps=(self.received-self.rate_start_count)/window
                self.rate_ratio=self.measured_sps/self.rate;self.rate_warning=not .8<=self.rate_ratio<=1.2
                if window>=15:
                    self.rate_start_time=now;self.rate_start_count=self.received
            if self.rate_warning!=self.last_rate_warning:
                from .diagnostics import event
                event('ry_skimmer','IQ sample clock '+repr(dict(declared_rate=self.rate,measured_complex_sps=round(self.measured_sps,1),ratio=round(self.rate_ratio,4),mismatch=self.rate_warning)))
                self.last_rate_warning=self.rate_warning
            self.last_snapshot=row
            return dict(rate=self.rate,measured_sps=self.measured_sps,rate_ratio=self.rate_ratio,rate_warning=self.rate_warning,center=self.center,received=self.received,processed=self.samples,
                lost_samples=self.lost_samples,dropped=self.dropped,queue_ms=1000*self.queued_seconds,
                input_sps=max(0,(row[1]-baseline[1])/elapsed),loss_percent=recent_loss,
                incoming=received,processed_time=processed,lost_time=lost,interval=elapsed,
                idle=now-self.last_arrival if self.last_arrival else now-self.started,
                elapsed=now-self.started)

    def set_monitor_center(self,hz):
        with self.lock:self.engine.set_monitor_center(hz)

    def manual(self,hz):
        with self.lock:self.engine.add_channel(hz)

    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=1.)

    def _take(self, timeout=.1):
        item=self.queue.get(timeout=timeout)
        with self.stats_lock:self.queued_seconds=max(0.,self.queued_seconds-len(item[0])/item[1])
        return item

    def _run(self):
        pending=None
        try:
            while not self.stop_event.is_set():
                try:item=pending if pending is not None else self._take()
                except queue.Empty:continue
                pending=None;parts=[item[0]];rate,center,gap=item[1:];size=len(item[0])
                deadline=time.monotonic()+.01
                while size<rate*self.batch_seconds and not self.stop_event.is_set():
                    try:other=self._take(timeout=max(.0001,deadline-time.monotonic()))
                    except queue.Empty:break
                    if other[1:3]!=(rate,center) or other[3]:pending=other;break
                    parts.append(other[0]);size+=len(other[0])
                    if time.monotonic()>=deadline:break
                data=parts[0] if len(parts)==1 else np.concatenate(parts)
                with self.lock:self.engine.feed(data,rate,center,gap)
                with self.stats_lock:self.samples+=size;self.processed_seconds+=size/rate
        except Exception as e:
            from .diagnostics import event
            event('ry_skimmer','DSP worker failed',error=e)
            self.error=str(e);self.stop_event.set()
