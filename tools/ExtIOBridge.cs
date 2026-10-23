// PSRTTY receive-only ExtIO host. Build x86 and x64 with .NET Framework csc.
// Interface: HDSDR LC_ExtIO_Types.h, 2016-11-23. No vendor code is included.
using System;
using System.IO;
using System.ComponentModel;
using System.Text;
using System.Threading;
using System.Collections.Concurrent;
using System.Runtime.InteropServices;
using System.Windows.Forms;

class ExtIOBridge {
    [DllImport("kernel32", CharSet=CharSet.Unicode, SetLastError=true)] static extern IntPtr LoadLibrary(string name);
    [DllImport("kernel32", CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr h,string name);
    [DllImport("kernel32", CharSet=CharSet.Unicode)] static extern bool SetDllDirectory(string name);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] [return:MarshalAs(UnmanagedType.I1)]
    delegate bool Init(StringBuilder name,StringBuilder model,ref int type);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] [return:MarshalAs(UnmanagedType.I1)] delegate bool Open();
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate void VoidFn();
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate int Start(int hz);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate int GetInt();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Callback(int count,int status,float offset,IntPtr data);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate void SetCallback(Callback callback);
    static IntPtr lib; static volatile bool quit; static int change;
    static int sampleType; static volatile int rate; static volatile int center; static volatile bool swap;
    static Callback callback; static GetInt getRate,getLO; static Start setLO; static long position;
    static int requestedCenter; static volatile bool tuning=true;
    static long queuedSamples, droppedSamples;
    const int BatchSamples=32768;
    static readonly object queueLock=new object();
    class Packet { public byte[] Bytes; public int Count,Rate,Center,Type; public bool Swap; public long Position; }
    static BlockingCollection<Packet> packets=new BlockingCollection<Packet>(4096);
    static T Fn<T>(string name,bool required=true) where T:class {
        IntPtr p=GetProcAddress(lib,name);
        if(p==IntPtr.Zero) {
            // x86 vendors sometimes export decorated stdcall names only.
            foreach(int size in new int[]{0,4,8,12}) {
                p=GetProcAddress(lib,"_"+name+"@"+size); if(p!=IntPtr.Zero)break;
            }
        }
        if(p==IntPtr.Zero) {if(required)throw new Exception("ExtIO export: "+name);return null;}
        return Marshal.GetDelegateForFunctionPointer(p,typeof(T)) as T;
    }
    static int Receive(int count,int status,float offset,IntPtr ptr) {
        if(count<0) {
            if(status==100||status==101||status==104)Interlocked.Exchange(ref change,1);
            if(status==116)swap=true; if(status==117)swap=false;
            return 0;
        }
        if(quit||count<=0||count>1048576||ptr==IntPtr.Zero)return 0;
        long samplePosition=Interlocked.Add(ref position,count)-count;
        if(tuning||Interlocked.CompareExchange(ref change,0,0)!=0) {Interlocked.Add(ref droppedSamples,count);return 0;}
        try {
            int bytes=sampleType==3?2:sampleType==5?3:(sampleType==9||sampleType==10)?1:4;
            // Keep the vendor callback short: only copy its ephemeral buffer.
            // Conversion and batching run on the pipe writer thread.
            lock(queueLock) {
                if(queuedSamples+count>Math.Max(rate/2,count)) {Interlocked.Add(ref droppedSamples,count);return 0;}
                byte[] src=new byte[count*2*bytes];Marshal.Copy(ptr,src,0,src.Length);
                if(packets.TryAdd(new Packet{Bytes=src,Count=count,Rate=rate,Center=center,Position=samplePosition,Type=sampleType,Swap=swap}))queuedSamples+=count;
                else Interlocked.Add(ref droppedSamples,count);
            }
        } catch(Exception e) {Console.Error.WriteLine(e.Message);quit=true;}
        return 0;
    }
    static Packet Take(int timeout) {
        Packet p;if(!packets.TryTake(out p,timeout))return null;
        lock(queueLock)queuedSamples-=p.Count;
        return p;
    }
    static byte[] ConvertIQ(Packet p) {
        int bytes=p.Type==3?2:p.Type==5?3:(p.Type==9||p.Type==10)?1:4;
        float[] dst=new float[p.Count*2];byte[] src=p.Bytes;
        for(int i=0;i<dst.Length;i++) {
            int k=i*bytes;float v;
            switch(p.Type) {
                case 3:v=BitConverter.ToInt16(src,k)/32768f;break;
                case 5:int n=src[k]|src[k+1]<<8|src[k+2]<<16;if((n&0x800000)!=0)n|=unchecked((int)0xff000000);v=n/8388608f;break;
                case 6:v=BitConverter.ToInt32(src,k)/8388608f;break;
                case 7:v=BitConverter.ToSingle(src,k);break;
                case 9:v=(src[k]-127.5f)/128f;break;
                case 10:v=unchecked((sbyte)src[k])/128f;break;
                case 11:v=BitConverter.ToInt32(src,k)/2147483648f;break;
                default:throw new Exception("IQ sample type");
            }
            dst[p.Swap?(i^1):i]=v;
        }
        byte[] output=new byte[dst.Length*4];Buffer.BlockCopy(dst,0,output,0,output.Length);return output;
    }
    static bool Contiguous(Packet a,Packet b) {
        return a.Rate==b.Rate&&a.Center==b.Center&&a.Position+a.Count==b.Position;
    }
    static void WritePackets(Stream stream) {
        Packet pending=null;
        using(var output=new BinaryWriter(stream)) {
            while(!quit||packets.Count>0||pending!=null) {
                Packet first=pending??Take(20);pending=null;if(first==null)continue;
                var group=new System.Collections.Generic.List<Packet>();group.Add(first);
                Packet last=first;int count=first.Count;
                var clock=System.Diagnostics.Stopwatch.StartNew();
                while(count<BatchSamples&&clock.ElapsedMilliseconds<20) {
                    Packet next=Take(1);if(next==null) {if(quit)break;continue;}
                    if(!Contiguous(last,next)) {pending=next;break;}
                    group.Add(next);count+=next.Count;last=next;
                }
                output.Write(new byte[]{82,89,73,81});output.Write(count);output.Write(first.Rate);output.Write((double)first.Center);output.Write(first.Position);
                foreach(Packet p in group)output.Write(ConvertIQ(p));
                output.Flush();
            }
        }
    }
    static void Tune(int hz) {
        if(setLO==null)throw new Exception("ExtIO export SetHWLO is required to set the IQ center");
        tuning=true;
        try {
            int result=setLO(hz);int actual=getLO();
            if(actual<=0)throw new Exception("ExtIO GetHWLO: "+actual);
            center=actual;
            Console.Error.WriteLine("[tune] requested="+hz+" actual="+center+" result="+result);
        } finally {tuning=false;}
    }
    // Leave the memory stream inspectable after BinaryWriter.Dispose().
    class NonClosingStream:Stream {
        readonly Stream stream;public NonClosingStream(Stream s){stream=s;}
        public override bool CanRead{get{return false;}}public override bool CanSeek{get{return false;}}public override bool CanWrite{get{return true;}}
        public override long Length{get{return stream.Length;}}public override long Position{get{return stream.Position;}set{throw new NotSupportedException();}}
        public override void Flush(){stream.Flush();}public override void Write(byte[] b,int o,int n){stream.Write(b,o,n);}
        public override int Read(byte[] b,int o,int n){throw new NotSupportedException();}
        public override long Seek(long o,SeekOrigin origin){throw new NotSupportedException();}public override void SetLength(long n){throw new NotSupportedException();}
    }
    static int SelfTest() {
        int[] types={3,5,6,7,9,10,11};
        byte[][] values={new byte[]{0,128,0,64},new byte[]{0,0,128,0,0,64},
            new byte[]{0,0,128,255,0,0,64,0},new byte[]{0,0,128,191,0,0,0,63},
            new byte[]{0,255},new byte[]{128,64},new byte[]{0,0,0,128,0,0,0,64}};
        for(int i=0;i<types.Length;i++) {
            sampleType=types[i];rate=48000;center=14090000;tuning=false;
            IntPtr ptr=Marshal.AllocHGlobal(values[i].Length);
            try {
                Marshal.Copy(values[i],0,ptr,values[i].Length);
                foreach(bool reversed in new bool[]{false,true}) {
                    swap=reversed;Receive(1,0,0,ptr);Packet p;
                    p=Take(0);if(p==null)throw new Exception("No IQ packet");
                    p.Bytes=ConvertIQ(p);
                    float a=BitConverter.ToSingle(p.Bytes,reversed?4:0);
                    float b=BitConverter.ToSingle(p.Bytes,reversed?0:4);
                    float expectedA=sampleType==9?-127.5f/128f:-1f;
                    float expectedB=sampleType==9?127.5f/128f:.5f;
                    if(a!=expectedA||b!=expectedB||p.Count!=1||p.Rate!=48000||p.Center!=14090000)
                        throw new Exception("IQ format "+sampleType);
                }
            } finally {Marshal.FreeHGlobal(ptr);}
        }
        // Verify that batching never combines discontinuous positions or centers.
        var pairA=new Packet{Rate=1920000,Center=14090000,Position=0,Count=512};
        var pairB=new Packet{Rate=1920000,Center=14090000,Position=512,Count=512};
        if(!Contiguous(pairA,pairB))throw new Exception("Contiguous batch");
        pairB.Position=1024;if(Contiguous(pairA,pairB))throw new Exception("Lost samples hidden");
        pairB.Position=512;pairB.Center=21090000;if(Contiguous(pairA,pairB))throw new Exception("Center boundary hidden");
        // 0.5 seconds of small input blocks fit; the next block is accounted.
        rate=1920000;sampleType=3;swap=false;position=0;droppedSamples=0;
        IntPtr buf=Marshal.AllocHGlobal(2048);
        try {for(int k=0;k<1876;k++)Receive(512,0,0,buf);}finally {Marshal.FreeHGlobal(buf);}
        if(queuedSamples!=960000||droppedSamples!=512)throw new Exception("Sample-duration queue limit");
        quit=true;
        using(var stream=new MemoryStream()) {
            WritePackets(new NonClosingStream(stream));stream.Position=0;
            using(var reader=new BinaryReader(stream)) {
                long expected=0;int frames=0;
                while(stream.Position<stream.Length) {
                    if(reader.ReadInt32()!=0x51495952)throw new Exception("Wire magic");
                    int count=reader.ReadInt32();int sr=reader.ReadInt32();double lo=reader.ReadDouble();long pos=reader.ReadInt64();
                    if(pos!=expected||sr!=1920000||count<512||count>BatchSamples||lo!=14090000)throw new Exception("Wire batch metadata");
                    if(reader.ReadBytes(count*8).Length!=count*8)throw new Exception("Wire payload");
                    expected+=count;frames++;
                }
                if(expected!=960000||frames>=100)throw new Exception("Wire batch total");
            }
        }
        quit=false;
        Console.WriteLine("ExtIO queue/boundaries and sample formats OK (16/24/24-in-32/float/U8/S8/32, IQ swap)");return 0;
    }
    [STAThread] static int Main(string[] args) {
        VoidFn stop=null,close=null;bool opened=false,started=false;
        try {
            if(args.Length==1&&args[0]=="--self-test")return SelfTest();
            if(args.Length!=2)throw new Exception("ExtIO DLL, center Hz");
            string path=Path.GetFullPath(args[0]);center=int.Parse(args[1]);
            Console.Error.WriteLine("[phase] DLL load: "+path);
            SetDllDirectory(Path.GetDirectoryName(path));lib=LoadLibrary(path);
            if(lib==IntPtr.Zero) {int code=Marshal.GetLastWin32Error();throw new Win32Exception(code,"LoadLibrary ("+code+"): "+new Win32Exception(code).Message+"; DLL or dependent driver/runtime");}
            Init init=Fn<Init>("InitHW");Open open=Fn<Open>("OpenHW");
            stop=Fn<VoidFn>("StopHW");close=Fn<VoidFn>("CloseHW");
            getRate=Fn<GetInt>("GetHWSR");getLO=Fn<GetInt>("GetHWLO");setLO=Fn<Start>("SetHWLO",false);
            var name=new StringBuilder(256);var model=new StringBuilder(256);
            Console.Error.WriteLine("[phase] InitHW");
            if(!init(name,model,ref sampleType))throw new Exception("InitHW");
            if(Array.IndexOf(new int[]{3,5,6,7,9,10,11},sampleType)<0)throw new Exception("ExtIO IQ sample type: "+sampleType);
            callback=Receive;Fn<SetCallback>("SetCallback")(callback);
            Console.Error.WriteLine("[phase] OpenHW");
            if(!open())throw new Exception("OpenHW");opened=true;
            Console.Error.WriteLine("[phase] Hardware open: "+name+" / "+model+" type="+sampleType);
            VoidFn gui=Fn<VoidFn>("ShowGUI",false);if(gui!=null)gui();
            rate=getRate();int wanted=center;
            if(setLO!=null)Tune(wanted);
            tuning=true;
            Console.Error.WriteLine("[phase] StartHW center="+wanted);
            int count=Fn<Start>("StartHW")(wanted);started=true;
            if(count<=0)throw new Exception("StartHW: "+count);
            rate=getRate();int lo=getLO();if(lo>0)center=lo;tuning=false;
            if(rate<6000||rate>8000000)throw new Exception("ExtIO sample rate: "+rate);
            // Some drivers only apply LO commands after streaming has started.
            if(setLO!=null)Tune(wanted);
            Console.Error.WriteLine("[phase] IQ receive start rate="+rate+" block="+count+" center="+center);
            var writer=new Thread(()=> {try {WritePackets(Console.OpenStandardOutput());}catch(Exception e){Console.Error.WriteLine("[error] IQ pipe: "+e.Message);quit=true;}});
            writer.IsBackground=true;writer.Start();
            var input=new Thread(()=>{
                try {string line;while((line=Console.ReadLine())!=null) {
                    int hz;if(line.StartsWith("CENTER ")&&int.TryParse(line.Substring(7),out hz)&&hz>0)Interlocked.Exchange(ref requestedCenter,hz);
                }}catch{}quit=true;
            });input.IsBackground=true;input.Start();
            var poll=System.Diagnostics.Stopwatch.StartNew();var stats=System.Diagnostics.Stopwatch.StartNew();
            while(!quit) {
                Application.DoEvents();
                int target=Interlocked.Exchange(ref requestedCenter,0);if(target>0)Tune(target);
                if(Interlocked.Exchange(ref change,0)!=0||poll.ElapsedMilliseconds>=500) {
                    int sr=getRate(),actual=getLO();
                    if(sr<6000||sr>8000000||actual<=0)throw new Exception("Invalid ExtIO rate/center: "+sr+" / "+actual);
                    if(sr!=rate||actual!=center)Console.Error.WriteLine("[state] rate="+sr+" center="+actual);
                    rate=sr;center=actual;poll.Restart();
                }
                if(stats.ElapsedMilliseconds>=10000) {
                    Console.Error.WriteLine("[stream] callback_samples="+Interlocked.Read(ref position)+" dropped_samples="+Interlocked.Read(ref droppedSamples)+" queue_samples="+Interlocked.Read(ref queuedSamples));stats.Restart();
                }
                Thread.Sleep(10);
            }
            return 0;
        } catch(Exception e) {Console.Error.WriteLine("[error] "+e.ToString());return 1;}
        finally {quit=true;if(started&&stop!=null)stop();if(opened&&close!=null)close();GC.KeepAlive(callback);}
    }
}
