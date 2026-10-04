import sys
from glb import *
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MP
from shapely.geometry import Polygon
from shapely.ops import unary_union
COLS={'FLOORS':'#dde3ea','WALLS':'#333','DOORS':'#c0392b','WINDOWS':'#3498db','KITCHEN':'#8e7f6e'}
Z={'FLOORS':0,'WALLS':3,'DOORS':4,'WINDOWS':4}
def topdown(path,out):
  j,B=load(path)
  matcol={m['name']:m['pbrMetallicRoughness']['baseColorFactor'][:3] for m in j['materials']}
  fig,ax=plt.subplots(figsize=(9,17))
  for n in j['nodes']:
    layer=n['extras']['layer']
    q=n.get('rotation',[0,0,0,1]); th=2*np.arctan2(q[1],q[3]); c,s=np.cos(th),np.sin(th)
    t=np.array(n.get('translation',[0,0,0]))
    prims=sorted(j['meshes'][n['mesh']]['primitives'],key=lambda p:acc(j,B,j['accessors'].index(j['accessors'][p['attributes']['POSITION']]) if False else p['attributes']['POSITION'])[:,1].max())
    for p in prims:
      P=acc(j,B,p['attributes']['POSITION']).astype(float)
      P=np.stack([P[:,0]*c+P[:,2]*s,P[:,1],-P[:,0]*s+P[:,2]*c],1)+t
      poly=unary_union([Polygon(tr[:,[0,2]]).buffer(0) for tr in P.reshape(-1,3,3) if Polygon(tr[:,[0,2]]).area>1e-6])
      col=COLS.get(layer) or matcol[j['materials'][p['material']]['name']]
      for g in getattr(poly,'geoms',[poly]):
        if not g.is_empty:
          ax.add_patch(MP(np.array(g.exterior.coords),fc=col,ec='k' if layer in('FURNITURE','KITCHEN') else 'none',lw=0.3,zorder=Z.get(layer,2)))
      if layer=='FLOORS':
        r=poly.representative_point(); ax.text(r.x,r.y,n['name'][-2:],fontsize=7,alpha=.5,zorder=5)
  ax.set_xlim(-5.6,5.6); ax.set_ylim(-11.1,11.1); ax.set_aspect('equal')
  plt.savefig(out,dpi=110,bbox_inches='tight')
topdown(sys.argv[1],sys.argv[2])
