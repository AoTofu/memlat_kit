/* memlat.c - CPU memory/cache latency (random pointer chase)
 * Windows (x86-64) と macOS (Apple Silicon) で同一アルゴリズム・同一乱数列で計測する。
 *  - 32bit インデックスを辿る (Apple の DMP=ポインタ先読みを回避。x86 も同条件)
 *  - ノード間隔 64B、全サイズで単一巡回のランダム順列 (同じ xorshift シード)
 *  - 各サイズ: ウォームアップ後、40ms 計測 x5 回の中央値 (引数で変更可)
 * usage:  Windows: memlat <logical_cpu> [maxMB=1024] [stride=64] [ms=40] [reps=5]
 *         macOS  : memlat p|e          [maxMB=1024] [stride=64] [ms=40] [reps=5]  (QoS で P/E コアを指定)
 */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <math.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <sys/mman.h>
#include <sys/sysctl.h>
#include <time.h>
#include <unistd.h>
#include <pthread.h>
#ifdef __APPLE__
#include <pthread/qos.h>
#endif
#endif

static uint64_t now_ns(void){
#ifdef _WIN32
  static LARGE_INTEGER f; LARGE_INTEGER c; if(!f.QuadPart) QueryPerformanceFrequency(&f);
  QueryPerformanceCounter(&c); return (uint64_t)((double)c.QuadPart*1e9/(double)f.QuadPart);
#elif defined(__APPLE__)
  return clock_gettime_nsec_np(CLOCK_UPTIME_RAW);
#else
  struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t); return (uint64_t)t.tv_sec*1000000000ull+t.tv_nsec;
#endif
}
static void* big_alloc(size_t n){
#ifdef _WIN32
  return VirtualAlloc(0,n,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
#else
  void*p=mmap(0,n,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON,-1,0); return p==MAP_FAILED?0:p;
#endif
}
static long page_size(void){
#ifdef _WIN32
  SYSTEM_INFO s; GetSystemInfo(&s); return s.dwPageSize;
#else
  return sysconf(_SC_PAGESIZE);
#endif
}
static void cpu_name(char*b,size_t n){
  b[0]=0;
#ifdef _WIN32
  HKEY k; DWORD sz=(DWORD)n;
  if(RegOpenKeyExA(HKEY_LOCAL_MACHINE,"HARDWARE\\DESCRIPTION\\System\\CentralProcessor\\0",0,KEY_READ,&k)==0){
    RegQueryValueExA(k,"ProcessorNameString",0,0,(LPBYTE)b,&sz); RegCloseKey(k);}
#elif defined(__APPLE__)
  sysctlbyname("machdep.cpu.brand_string",b,&n,0,0);
#endif
  while(*b==' ') memmove(b,b+1,strlen(b));
  for(size_t l=strlen(b); l && b[l-1]==' '; l--) b[l-1]=0;
}
static int select_core(const char*a,char*desc){
#ifdef _WIN32
  int c=atoi(a);
  SetPriorityClass(GetCurrentProcess(),HIGH_PRIORITY_CLASS);
  SetThreadPriority(GetCurrentThread(),THREAD_PRIORITY_HIGHEST);
  if(!SetThreadAffinityMask(GetCurrentThread(),(DWORD_PTR)1<<c)) return -1;
  sprintf(desc,"affinity logical CPU %d",c); return 0;
#elif defined(__APPLE__)
  qos_class_t q = (a[0]=='e'||a[0]=='E') ? QOS_CLASS_BACKGROUND : QOS_CLASS_USER_INTERACTIVE;
  if(pthread_set_qos_class_self_np(q,0)) return -1;
  sprintf(desc,"QoS %s",q==QOS_CLASS_BACKGROUND?"BACKGROUND (E-core)":"USER_INTERACTIVE (P-core)"); return 0;
#else
  sprintf(desc,"no affinity"); return 0;
#endif
}
/* 依存加算チェーンで実効クロックを推定 (add のレイテンシ=1cycle は x86/Apple 共通) */
#if defined(__x86_64__) || defined(_M_X64)
#define ADD1 "add $1, %0\n\t"
#else
#define ADD1 "add %0, %0, #1\n\t"
#endif
#define ADD8 ADD1 ADD1 ADD1 ADD1 ADD1 ADD1 ADD1 ADD1
static double measure_ghz(void){
  double best=0;
  for(int r=0;r<5;r++){
    uint64_t x=0, it=20000000, t0=now_ns();
    for(uint64_t i=0;i<it;i++) __asm__ volatile(ADD8 ADD8 ADD8 ADD8 : "+r"(x));
    double g=(double)it*32/(double)(now_ns()-t0); if(g>best)best=g;
  }
  return best;
}
static uint64_t rng=0x9E3779B97F4A7C15ULL;
static uint64_t xr(void){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return rng;}
static int cmpd(const void*a,const void*b){double x=*(double*)a,y=*(double*)b;return x<y?-1:x>y;}

int main(int argc,char**argv){
  if(argc<2){fprintf(stderr,"usage: memlat <cpu|p|e> [maxMB=1024] [stride=64] [ms=40] [reps=5]\n");return 1;}
  char desc[128],name[128]; size_t maxmb=argc>2?atoi(argv[2]):1024, stride=argc>3?atoi(argv[3]):64;
  int ms=argc>4?atoi(argv[4]):40, reps=argc>5?atoi(argv[5]):5;
  if(stride<8||stride%4) stride=64; if(ms<1) ms=40; if(reps<1) reps=5; if(reps>101) reps=101;
  if(select_core(argv[1],desc)){fprintf(stderr,"core select failed\n");return 1;}
  size_t maxb=maxmb<<20, sw=stride/4;
  uint32_t*a=big_alloc(maxb); uint32_t*idx=malloc((maxb/stride)*4);
  if(!a||!idx){fprintf(stderr,"alloc failed\n");return 1;}
  long ps=page_size(); for(size_t i=0;i<maxb;i+=ps) ((volatile char*)a)[i]=1;
  double ghz0=measure_ghz();
  cpu_name(name,sizeof name);
  printf("# cpu: %s\n# core: %s\n# page_size: %ld\n# stride: %zu\n# ms: %d\n# reps: %d\n# ghz_start: %.3f\n",name,desc,ps,stride,ms,reps,ghz0);
  printf("kb,ns\n"); fflush(stdout);
  uint32_t p=0;
  for(int k=0;;k++){
    double kb=4.0*pow(2.0,k/8.0); if(kb*1024>maxb*1.0001) break;
    size_t n=(size_t)(kb*1024/stride); if(n<2)n=2;
    for(size_t i=0;i<n;i++) idx[i]=(uint32_t)i;
    for(size_t i=n-1;i>0;i--){size_t j=xr()%(i+1);uint32_t t=idx[i];idx[i]=idx[j];idx[j]=t;}
    for(size_t i=0;i<n;i++) a[(size_t)idx[i]*sw]=(uint32_t)((size_t)idx[(i+1)%n]*sw);
    p=(uint32_t)((size_t)idx[0]*sw);
    for(size_t i=0;i<n*2 && i<20000000;i++) p=a[p];
    double r[101];
    for(int rep=0;rep<reps;rep++){
      uint64_t it=0,t0=now_ns(),t1;
      do{ for(int i=0;i<25000;i++){p=a[p];p=a[p];p=a[p];p=a[p];} it+=100000; t1=now_ns(); }
      while(t1-t0<(uint64_t)ms*1000000ull);
      r[rep]=(double)(t1-t0)/(double)it;
    }
    qsort(r,reps,sizeof(double),cmpd);
    printf("%.2f,%.3f\n",kb,r[reps/2]+(p==0xFFFFFFFFu)); fflush(stdout);
  }
  printf("# ghz_end: %.3f\n",measure_ghz());
  return 0;
}
