"""Helpers for the WAV tests: write a stereo I/Q WAV in any common sample format (with an optional auxi chunk)."""
import numpy as np, struct, sys
from scipy import signal
def write_wav(path, z, fs, bits=16, kind='pcm', auxi_center=None, swap=False, extensible=False, data_size=None, mono=False):
    I, Q = (z.imag, z.real) if swap else (z.real, z.imag)
    st = np.empty(len(z)*2, dtype=np.float64); st[0::2]=I; st[1::2]=Q
    if kind=='float':
        data = st.astype('<f4').tobytes() if bits==32 else st.astype('<f8').tobytes(); tag=3
    elif bits==8: data=np.clip(np.round(st*127.5+127.5),0,255).astype(np.uint8).tobytes(); tag=1
    elif bits==16: data=np.clip(np.round(st*32767),-32768,32767).astype('<i2').tobytes(); tag=1
    elif bits==24:
        v=np.clip(np.round(st*8388607),-8388608,8388607).astype(np.int32)&0xFFFFFF
        b=np.empty((len(v),3),dtype=np.uint8); b[:,0]=v&255; b[:,1]=(v>>8)&255; b[:,2]=(v>>16)&255; data=b.tobytes(); tag=1
    elif bits==32: data=np.clip(np.round(st*2147483647),-2147483648,2147483647).astype('<i4').tobytes(); tag=1
    if mono:
        data = data[:len(data)//2]
    ch=1 if mono else 2; ba=ch*bits//8
    if extensible:
        fmt=struct.pack('<HHIIHH',0xFFFE,ch,int(fs),int(fs)*ba,ba,bits)+struct.pack('<HHI',22,bits,3)+struct.pack('<H',tag)+bytes.fromhex('000000001000800000aa00389b71')
    else: fmt=struct.pack('<HHIIHH',tag,ch,int(fs),int(fs)*ba,ba,bits)
    chunks=b'fmt '+struct.pack('<I',len(fmt))+fmt
    if auxi_center is not None:
        st_=struct.pack('<8H',2026,10,2,4,10,35,21,0)
        aux=st_+st_+struct.pack('<9I',int(auxi_center),int(fs),0,int(fs),0,0,0,0,0)
        chunks+=b'auxi'+struct.pack('<I',len(aux))+aux
    declared = len(data) if data_size is None else data_size
    chunks+=b'data'+struct.pack('<I',declared)+data+(b'\0' if len(data)%2 else b'')
    open(path,'wb').write(b'RIFF'+struct.pack('<I',4+len(chunks))+b'WAVE'+chunks)
def shift(z, fs, f):
    n=np.arange(len(z)); return (z*np.exp(2j*np.pi*f*n/fs)).astype(np.complex64)
