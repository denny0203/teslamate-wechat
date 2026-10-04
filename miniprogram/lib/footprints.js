const {mapData}=require('./detail');
function closestRoute(routes,latitude,longitude){let winner=null,min=Infinity;const k=Math.cos(Number(latitude)*Math.PI/180);for(const r of routes){for(const segment of r.payload.segments||[]){for(let i=1;i<segment.length;i++){const a=segment[i-1],b=segment[i],x=(Number(a.longitude)-longitude)*k,y=Number(a.latitude)-latitude,dx=(Number(b.longitude)-Number(a.longitude))*k,dy=Number(b.latitude)-Number(a.latitude),len=dx*dx+dy*dy,t=len?Math.max(0,Math.min(1,-(x*dx+y*dy)/len)):0,d=(x+t*dx)**2+(y+t*dy)**2;if(d<min){min=d;winner=r.id;}}}}return min<(.001)**2?winner:null;}
// Simplify each continuous segment independently; never bridge a sampling gap.
function simplify(points,meters){
 if(points.length<3)return points;
 const k=Math.cos(points[0].latitude*Math.PI/180),tolerance=(meters/111320)**2,keep=new Set([0,points.length-1]),stack=[[0,points.length-1]];
 while(stack.length){const [first,last]=stack.pop(),a=points[first],b=points[last],dx=(b.longitude-a.longitude)*k,dy=b.latitude-a.latitude,len=dx*dx+dy*dy;let max=tolerance,index=-1;
 for(let i=first+1;i<last;i++){const x=(points[i].longitude-a.longitude)*k,y=points[i].latitude-a.latitude,t=len?Math.max(0,Math.min(1,(x*dx+y*dy)/len)):0,d=(x-t*dx)**2+(y-t*dy)**2;if(d>max){max=d;index=i;}}
 if(index>=0){keep.add(index);stack.push([first,index],[index,last]);}}
 return points.filter((_,i)=>keep.has(i));
}
function compose(routes){
 const original=[],fitPoints=[],markers=[];
 for(const r of routes){const data=mapData(r.payload);original.push(...data.polylines.map(line=>({...line,width:2,borderWidth:0})));fitPoints.push(...data.fitPoints);
 for(const marker of data.markers)markers.push({id:markers.length+1,latitude:Number(marker.latitude),longitude:Number(marker.longitude),iconPath:'/assets/footprint-dot-fine.png',width:24,height:24,anchor:{x:.5,y:.5}});}
 let polyline=original.map(l=>({...l,points:simplify(l.points,8)}));
 // A complete native map property update must stay within the bridge size budget.
 for(let meters=16;polyline.reduce((sum,l)=>sum+l.points.length,0)>9000&&meters<=256;meters*=2)polyline=original.map(l=>({...l,points:simplify(l.points,meters)}));
 if(!fitPoints.length)return {polyline,markers,fitPoints:[]};
 const bounds=fitPoints.reduce((b,p)=>({minLat:Math.min(b.minLat,p.latitude),maxLat:Math.max(b.maxLat,p.latitude),minLon:Math.min(b.minLon,p.longitude),maxLon:Math.max(b.maxLon,p.longitude)}),{minLat:90,maxLat:-90,minLon:180,maxLon:-180});
 return {polyline,markers,fitPoints:[{latitude:bounds.minLat,longitude:bounds.minLon},{latitude:bounds.maxLat,longitude:bounds.maxLon}]};
}
module.exports={closestRoute,compose,simplify};
