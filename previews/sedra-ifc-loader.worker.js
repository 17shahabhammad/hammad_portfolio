import * as WEBIFC from "https://cdn.jsdelivr.net/npm/web-ifc@0.0.77/web-ifc-api.js";

const api = new WEBIFC.IfcAPI();
api.SetWasmPath("https://cdn.jsdelivr.net/npm/web-ifc@0.0.77/", true);

let initError = null;
const ready = api.Init().then(
  () => self.postMessage({type:"ready"}),
  error => {
    initError = error;
    self.postMessage({
      type:"error",
      message:"IFC engine could not start: " + (error?.message || String(error))
    });
    throw error;
  }
);

self.onmessage = async event => {
  const message = event.data || {};
  if (message.type !== "load") return;

  let modelID = null;
  try {
    await ready;
    if (initError) throw initError;

    self.postMessage({type:"status", message:"Opening IFC model in background…"});
    const bytes = new Uint8Array(message.buffer);
    modelID = api.OpenModel(bytes, {COORDINATE_TO_ORIGIN:true});

    self.postMessage({type:"status", message:"Generating model geometry in background…"});
    let meshCount = 0;
    let triangleCount = 0;

    api.StreamAllMeshes(modelID, (flatMesh, index, total) => {
      const batch = [];
      const placed = flatMesh.geometries;

      for (let i = 0; i < placed.size(); i++) {
        const pg = placed.get(i);
        const ifcGeometry = api.GetGeometry(modelID, pg.geometryExpressID);
        const verts = api.GetVertexArray(
          ifcGeometry.GetVertexData(),
          ifcGeometry.GetVertexDataSize()
        );
        const sourceIndices = api.GetIndexArray(
          ifcGeometry.GetIndexData(),
          ifcGeometry.GetIndexDataSize()
        );

        const positions = new Float32Array(verts.length / 2);
        const normals = new Float32Array(verts.length / 2);

        for (let j = 0; j < verts.length; j += 6) {
          const k = (j / 6) * 3;
          positions[k] = verts[j];
          positions[k + 1] = verts[j + 1];
          positions[k + 2] = verts[j + 2];
          normals[k] = verts[j + 3];
          normals[k + 1] = verts[j + 4];
          normals[k + 2] = verts[j + 5];
        }

        const indices = new Uint32Array(sourceIndices);
        batch.push({
          positions,
          normals,
          indices,
          color: [pg.color.x, pg.color.y, pg.color.z, pg.color.w],
          transform: Array.from(pg.flatTransformation)
        });

        meshCount++;
        triangleCount += Math.floor(indices.length / 3);
        if (typeof ifcGeometry.delete === "function") ifcGeometry.delete();
      }

      if (batch.length) {
        const transfers = [];
        for (const item of batch) {
          transfers.push(item.positions.buffer, item.normals.buffer, item.indices.buffer);
        }
        self.postMessage({type:"batch", index:index + 1, total, meshes:batch}, transfers);
      }
    }, true);

    api.CloseModel(modelID);
    modelID = null;
    self.postMessage({type:"done", meshCount, triangleCount});
  } catch (error) {
    if (modelID !== null) {
      try { api.CloseModel(modelID); } catch (_) {}
    }
    self.postMessage({type:"error", message:error?.message || String(error)});
  }
};
