import { EventEmitter } from "node:events";
import { PassThrough } from "node:stream";
import { beforeEach, describe, expect, it, vi } from "vitest";

const spawnMock = vi.hoisted(() => vi.fn());

vi.mock("node:child_process", () => ({
  spawn: spawnMock
}));

vi.mock("electron-log", () => ({
  default: {
    info: vi.fn(),
    warn: vi.fn()
  }
}));

vi.mock("../path.js", () => ({
  resolveSidecarCommand: () => ({ command: "python", args: ["-m", "sabi", "sidecar"], cwd: "." })
}));

function fakeChild() {
  const child = new EventEmitter() as EventEmitter & {
    stdin: PassThrough;
    stdout: PassThrough;
    stderr: PassThrough;
    killed: boolean;
    kill: ReturnType<typeof vi.fn>;
    pid: number;
  };
  child.stdin = new PassThrough();
  child.stdout = new PassThrough();
  child.stderr = new PassThrough();
  child.killed = false;
  child.pid = 1234;
  child.kill = vi.fn(() => {
    child.killed = true;
    child.emit("exit", 0, null);
    return true;
  });
  return child;
}

describe("SidecarProcess", () => {
  beforeEach(() => {
    spawnMock.mockClear();
  });

  it("starts and stops the sidecar child process", async () => {
    const child = fakeChild();
    spawnMock.mockReturnValue(child);
    const { SidecarProcess } = await import("../process.js");
    const sidecar = new SidecarProcess();
    sidecar.start();
    expect(spawnMock).toHaveBeenCalledWith("python", ["-m", "sabi", "sidecar"], expect.any(Object));
    expect(spawnMock.mock.calls[0][2].env).toMatchObject({ SABI_SIDECAR_NO_HOTKEY: "1" });
    expect(sidecar.snapshot()).toMatchObject({ state: "starting", pid: 1234 });
    await sidecar.stop();
    expect(child.kill).toHaveBeenCalled();
    expect(sidecar.snapshot()).toMatchObject({ state: "stopped" });
  });

  it("marks unexpected exits disconnected and schedules a restart", async () => {
    vi.useFakeTimers();
    const child = fakeChild();
    spawnMock.mockReturnValue(child);
    const { SidecarProcess } = await import("../process.js");
    const sidecar = new SidecarProcess();
    sidecar.start();
    child.emit("exit", 1, null);
    expect(sidecar.snapshot()).toMatchObject({ state: "disconnected", restarts: 1 });
    vi.advanceTimersByTime(1_000);
    expect(spawnMock).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
  });
});
