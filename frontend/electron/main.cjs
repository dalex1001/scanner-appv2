const { app, BrowserWindow } = require("electron");
const { spawn } = require("node:child_process");
const path = require("node:path");

let apiProcess;

function startBackend() {
  const executable = path.join(process.resourcesPath, "backend", "scanner-api.exe");
  apiProcess = spawn(executable, [], { stdio: "ignore", windowsHide: true });
  apiProcess.on("error", (error) => {
    console.error("Failed to start Scanner API:", error);
  });
}

function createWindow() {
  const window = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  window.loadFile(path.join(__dirname, "..", "www", "index.html"));
}

app.whenReady().then(() => {
  startBackend();
  createWindow();
});

app.on("before-quit", () => {
  if (apiProcess && !apiProcess.killed) {
    apiProcess.kill();
  }
});