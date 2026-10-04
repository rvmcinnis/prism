import struct,json,numpy as np
def load(path):
  d=open(path,'rb').read()
  cl=struct.unpack('<I',d[12:16])[0]; j=json.loads(d[20:20+cl])
  o=20+cl; bl=struct.unpack('<I',d[o:o+4])[0]; B=d[o+8:o+8+bl]
  return j,B
def acc(j,B,i):
  a=j['accessors'][i]; bv=j['bufferViews'][a['bufferView']]
  n={'SCALAR':1,'VEC2':2,'VEC3':3}[a['type']]; dt={5126:np.float32,5125:np.uint32,5123:np.uint16}[a['componentType']]
  off=bv.get('byteOffset',0)+a.get('byteOffset',0)
  r=np.frombuffer(B,dtype=dt,count=a['count']*n,offset=off)
  return r.reshape(-1,n) if n>1 else r
