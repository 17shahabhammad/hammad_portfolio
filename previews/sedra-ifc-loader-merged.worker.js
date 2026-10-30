import * as WEBIFC from "https://cdn.jsdelivr.net/npm/web-ifc@0.0.77/web-ifc-api.js";

const api = new WEBIFC.IfcAPI();
api.SetWasmPath("https://cdn.jsdelivr.net/npm/web-ifc@0.0.77/", true);

let initError = null;
const ready = api.Init().then(
  () => self.postMessage({type:"ready"}),
  error => {
    initError = error;
    self.postMessage({type:"error", message:"IFC engine could not start: " + (error?.message || String(error))});
    throw error;
  }
);

const IDENTITY = [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1];

function colorKey(color) {
  return [color.x,color.y,color.z,color.w].map(v => Number(v ?? 1).toFixed(4)).join("|");
}

function makeBucket(color) {
  return {
    color:[color.x,color.y,color.z,color.w],
    positions:[],
    normals:[],
    indices:[],
    vertexCount:0,
    indexCount:0
  };
}

function flushBuckets(buckets, batchNumber, sourceCount) {
  const meshes=[];
  const transfers=[];
  for (const bucket of buckets.values()) {
    if (!bucket.vertexCount || !bucket.indexCount) continue;

    const positions=new Float32Array(bucket.vertexCount*3);
    const normals=new Float32Array(bucket.vertexCount*3);
    const indices=new Uint32Array(bucket.indexCount);

    let p=0, n=0, t=0;
    for (const chunk of bucket.positions) { positions.set(chunk,p); p+=chunk.length; }
    for (const chunk of bucket.normals) { normals.set(chunk,n); n+=chunk.length; }
    for (const chunk of bucket.indices) { indices.set(chunk,t); t+=chunk.length; }

    meshes.push({
      positions,
      normals,
      indices,
      color:bucket.color,
      transform:IDENTITY
    });
    transfers.push(positions.buffer,normals.buffer,indices.buffer);
  }

  if (meshes.length) {
    self.postMessage({
      type:"batch",
      index:batchNumber,
      total:0,
      sourceObjects:sourceCount,
      meshes
    },transfers);
  }
  buckets.clear();
}

self.onmessage = async event => {
  const message=event.data||{};
  if (message.type!=="load") return;

  let modelID=null;
  try {
    await ready;
    if (initError) throw initError;

    self.postMessage({type:"status",message:"Opening IFC model in background…"});
    const bytes=new Uint8Array(message.buffer);
    modelID=api.OpenModel(bytes,{COORDINATE_TO_ORIGIN:true});

    self.postMessage({type:"status",message:"Reading building geometry and combining mesh pieces…"});
    const buckets=new Map();
    let meshCount=0;
    let triangleCount=0;
    let sourceObjectCount=0;
    let batchNumber=0;
    const FLUSH_EVERY_OBJECTS=48;

    const addPlacedGeometry=(pg)=>{
      const ifcGeometry=api.GetGeometry(modelID,pg.geometryExpressID);
      const verts=api.GetVertexArray(ifcGeometry.GetVertexData(),ifcGeometry.GetVertexDataSize());
      const sourceIndices=api.GetIndexArray(ifcGeometry.GetIndexData(),ifcGeometry.GetIndexDataSize());
      if (!verts || !verts.length || !sourceIndices || !sourceIndices.length) {
        if (typeof ifcGeometry.delete==="function") ifcGeometry.delete();
        return;
      }

      const color=pg.color||{x:.78,y:.78,z:.76,w:1};
      const key=colorKey(color);
      let bucket=buckets.get(key);
      if(!bucket){bucket=makeBucket(color);buckets.set(key,bucket);}

      const matrix=pg.flatTransformation||IDENTITY;
      const vertexCount=verts.length/6;
      const positions=new Float32Array(vertexCount*3);
      const normals=new Float32Array(vertexCount*3);

      for(let j=0;j<verts.length;j+=6){
        const k=(j/6)*3;
        const x=verts[j], y=verts[j+1], z=verts[j+2];
        const nx=verts[j+3], ny=verts[j+4], nz=verts[j+5];

        positions[k]   = matrix[0]*x + matrix[4]*y + matrix[8]*z + matrix[12];
        positions[k+1] = matrix[1]*x + matrix[5]*y + matrix[9]*z + matrix[13];
        positions[k+2] = matrix[2]*x + matrix[6]*y + matrix[10]*z + matrix[14];

        let tx=matrix[0]*nx + matrix[4]*ny + matrix[8]*nz;
        let ty=matrix[1]*nx + matrix[5]*ny + matrix[9]*nz;
        let tz=matrix[2]*nx + matrix[6]*ny + matrix[10]*nz;
        const length=Math.hypot(tx,ty,tz)||1;
        normals[k]=tx/length; normals[k+1]=ty/length; normals[k+2]=tz/length;
      }

      const indexOffset=bucket.vertexCount;
      const indices=new Uint32Array(sourceIndices.length);
      for(let i=0;i<sourceIndices.length;i++) indices[i]=sourceIndices[i]+indexOffset;

      bucket.positions.push(positions);
      bucket.normals.push(normals);
      bucket.indices.push(indices);
      bucket.vertexCount+=vertexCount;
      bucket.indexCount+=indices.length;
      meshCount++;
      triangleCount+=Math.floor(indices.length/3);

      if(typeof ifcGeometry.delete==="function") ifcGeometry.delete();
    };

    api.StreamAllMeshes(modelID,(flatMesh)=>{
      const placed=flatMesh.geometries;
      for(let i=0;i<placed.size();i++) addPlacedGeometry(placed.get(i));
      sourceObjectCount++;

      if(sourceObjectCount % FLUSH_EVERY_OBJECTS===0){
        batchNumber++;
        flushBuckets(buckets,batchNumber,sourceObjectCount);
        self.postMessage({
          type:"status",
          message:"Combined "+sourceObjectCount.toLocaleString()+" model objects · "+meshCount.toLocaleString()+" geometry pieces…"
        });
      }
    },true);

    if(buckets.size){
      batchNumber++;
      flushBuckets(buckets,batchNumber,sourceObjectCount);
    }

    api.CloseModel(modelID);
    modelID=null;
    self.postMessage({
      type:"done",
      meshCount,
      triangleCount,
      sourceObjectCount,
      batchCount:batchNumber
    });
  } catch(error) {
    if(modelID!==null){try{api.CloseModel(modelID);}catch(_){}}
    self.postMessage({type:"error",message:error?.message||String(error)});
  }
};
