
import { app, BrowserWindow, ipcMain } from "electron";
import { fileURLToPath } from "url";
import { dirname, join } from "path";
import { spawn } from "child_process";


const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

let win;

function createWindow() {
  win = new BrowserWindow({
    width: 1100,
    height: 750,
    webPreferences: {
      preload: join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: false, 
    }
  });

  win.loadFile(join(__dirname, "renderer", "index.html"));
  // win.webContents.openDevTools(); // optional
}

app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

// ------------ Python bridge ------------
ipcMain.handle("ml:predict", async (_event, payload) => {
  return runPython("predict_stub.py", payload);
});

function runPython(scriptPath, payloadObj) {
  return new Promise((resolve, reject) => {
    const py = spawn(process.platform === "win32" ? "python" : "python3", [scriptPath], {
      cwd: __dirname
    });

    let out = "";
    let err = "";

    py.stdout.on("data", (d) => (out += d.toString()));
    py.stderr.on("data", (d) => (err += d.toString()));

    py.on("close", (code) => {
      if (code === 0) {
        try {
          const json = JSON.parse(out);
          resolve(json);
        } catch (e) {
          reject(new Error("Invalid JSON from Python: " + out + "\n" + e));
        }
      } else {
        reject(new Error(err || `Python exited with code ${code}`));
      }
    });

    // send JSON payload to Python via stdin
    py.stdin.write(JSON.stringify(payloadObj));
    py.stdin.end();
  });
}
