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
    static Callback callback; static GetInt getRate,getLO; static long position;
    class Packet { public byte[] Bytes; public int Count,Rate,Center; public long Position; }
    static BlockingCollection<Packet> packets=new BlockingCollection<Packet>(8);
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
        try {
            int bytes=sampleType==3?2:sampleType==5?3:(sampleType==9||sampleType==10)?1:4;
            byte[] src=new byte[count*2*bytes];Marshal.Copy(ptr,src,0,src.Length);
            float[] dst=new float[count*2];
            for(int i=0;i<dst.Length;i++) {
                int k=i*bytes; float v;
                switch(sampleType) {
                    case 3:v=BitConverter.ToInt16(src,k)/32768f;break;
                    case 5:int n=src[k]|src[k+1]<<8|src[k+2]<<16; if((n&0x800000)!=0)n|=unchecked((int)0xff000000);v=n/8388608f;break;
                    case 6:v=BitConverter.ToInt32(src,k)/8388608f;break;
                    case 7:v=BitConverter.ToSingle(src,k);break;
                    case 9:v=(src[k]-127.5f)/128f;break;
                    case 10:v=unchecked((sbyte)src[k])/128f;break;
                    case 11:v=BitConverter.ToInt32(src,k)/2147483648f;break;
                    default:return 0;
                }
                dst[swap?(i^1):i]=v;
            }
            byte[] output=new byte[dst.Length*4];Buffer.BlockCopy(dst,0,output,0,output.Length);
            packets.TryAdd(new Packet{Bytes=output,Count=count,Rate=rate,Center=center,Position=samplePosition});
        } catch(Exception e) {Console.Error.WriteLine(e.Message);quit=true;}
        return 0;
    }
    static int SelfTest() {
        int[] types={3,5,6,7,9,10,11};
        byte[][] values={new byte[]{0,128,0,64},new byte[]{0,0,128,0,0,64},
            new byte[]{0,0,128,255,0,0,64,0},new byte[]{0,0,128,191,0,0,0,63},
            new byte[]{0,255},new byte[]{128,64},new byte[]{0,0,0,128,0,0,0,64}};
        for(int i=0;i<types.Length;i++) {
            sampleType=types[i];rate=48000;center=14090000;
            IntPtr ptr=Marshal.AllocHGlobal(values[i].Length);
            try {
                Marshal.Copy(values[i],0,ptr,values[i].Length);
                foreach(bool reversed in new bool[]{false,true}) {
                    swap=reversed;Receive(1,0,0,ptr);Packet p;
                    if(!packets.TryTake(out p))throw new Exception("No IQ packet");
                    float a=BitConverter.ToSingle(p.Bytes,reversed?4:0);
                    float b=BitConverter.ToSingle(p.Bytes,reversed?0:4);
                    float expectedA=sampleType==9?-127.5f/128f:-1f;
                    float expectedB=sampleType==9?127.5f/128f:.5f;
                    if(a!=expectedA||b!=expectedB||p.Count!=1||p.Rate!=48000||p.Center!=14090000)
                        throw new Exception("IQ format "+sampleType);
                }
            } finally {Marshal.FreeHGlobal(ptr);}
        }
        Console.WriteLine("ExtIO sample formats OK (16/24/24-in-32/float/U8/S8/32, IQ swap)");return 0;
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
            getRate=Fn<GetInt>("GetHWSR");getLO=Fn<GetInt>("GetHWLO");
            var name=new StringBuilder(256);var model=new StringBuilder(256);
            Console.Error.WriteLine("[phase] InitHW");
            if(!init(name,model,ref sampleType))throw new Exception("InitHW");
            if(Array.IndexOf(new int[]{3,5,6,7,9,10,11},sampleType)<0)throw new Exception("ExtIO IQ sample type: "+sampleType);
            callback=Receive;Fn<SetCallback>("SetCallback")(callback);
            Console.Error.WriteLine("[phase] OpenHW");
            if(!open())throw new Exception("OpenHW");opened=true;
            Console.Error.WriteLine("[phase] Hardware open: "+name+" / "+model+" type="+sampleType);
            VoidFn gui=Fn<VoidFn>("ShowGUI",false);if(gui!=null)gui();
            rate=getRate();
            Console.Error.WriteLine("[phase] StartHW center="+center);
            int count=Fn<Start>("StartHW")(center);started=true;
            if(count<=0)throw new Exception("StartHW: "+count);
            rate=getRate();int lo=getLO();if(lo>0)center=lo;
            if(rate<6000||rate>8000000)throw new Exception("ExtIO sample rate: "+rate);
            Console.Error.WriteLine("[phase] IQ receive start rate="+rate+" block="+count+" center="+center);
            var writer=new Thread(()=> {
                try {using(var output=new BinaryWriter(Console.OpenStandardOutput())) {
                    foreach(Packet p in packets.GetConsumingEnumerable()) {
                        output.Write(new byte[]{82,89,73,81});output.Write(p.Count);output.Write(p.Rate);output.Write((double)p.Center);output.Write(p.Position);output.Write(p.Bytes);output.Flush();
                    }
                }}catch{quit=true;}
            });writer.IsBackground=true;writer.Start();
            var input=new Thread(()=>{try{while(Console.Read()!=-1){}}catch{}quit=true;});input.IsBackground=true;input.Start();
            while(!quit) {
                Application.DoEvents();
                if(Interlocked.Exchange(ref change,0)!=0) {rate=getRate();center=getLO();}
                Thread.Sleep(10);
            }
            return 0;
        } catch(Exception e) {Console.Error.WriteLine("[error] "+e.ToString());return 1;}
        finally {quit=true;if(started&&stop!=null)stop();if(opened&&close!=null)close();GC.KeepAlive(callback);}
    }
}
