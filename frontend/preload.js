
import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("ml", {
  predict: (payload) => ipcRenderer.invoke("ml:predict", payload)
});
