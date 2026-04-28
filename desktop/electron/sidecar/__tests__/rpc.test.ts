import { PassThrough } from "node:stream";
import { describe, expect, it, vi } from "vitest";

import { JsonRpcClient } from "../rpc.js";

function makeClient(timeoutMs = 100) {
  const stdout = new PassThrough();
  const stdin = new PassThrough();
  const writes: string[] = [];
  stdin.on("data", (chunk) => writes.push(chunk.toString()));
  return { client: new JsonRpcClient(stdout, stdin, timeoutMs), stdout, writes };
}

describe("JsonRpcClient", () => {
  it("frames requests and resolves matching responses", async () => {
    const { client, stdout, writes } = makeClient();
    const promise = client.call("meta.version");
    expect(JSON.parse(writes[0])).toMatchObject({ jsonrpc: "2.0", id: 1, method: "meta.version" });
    stdout.write('{"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n');
    await expect(promise).resolves.toEqual({ ok: true });
  });

  it("routes notifications to subscribers", () => {
    const { client, stdout } = makeClient();
    const listener = vi.fn();
    client.on("notification", listener);
    stdout.write('{"jsonrpc":"2.0","method":"probe.progress","params":{"step":"x"}}\n');
    expect(listener).toHaveBeenCalledWith({
      method: "probe.progress",
      params: { step: "x" }
    });
  });

  it("ignores non-json stdout without failing pending requests", async () => {
    const { client, stdout } = makeClient();
    const errorListener = vi.fn();
    client.on("error", errorListener);

    const promise = client.call("dictation.fused.stop");
    stdout.write("I LOVE YOU\n");
    stdout.write('{"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n');

    await expect(promise).resolves.toEqual({ ok: true });
    expect(errorListener).not.toHaveBeenCalled();
  });

  it("rejects json-rpc errors", async () => {
    const { client, stdout } = makeClient();
    const promise = client.call("missing.method");
    stdout.write('{"jsonrpc":"2.0","id":1,"error":{"code":-32601,"message":"nope"}}\n');
    await expect(promise).rejects.toThrow("JSON-RPC -32601: nope");
  });

  it("rejects timed-out requests", async () => {
    const { client } = makeClient(1);
    await expect(client.call("slow.method")).rejects.toThrow("timed out");
  });

  it("does not use the short timeout for model downloads", async () => {
    const { client, stdout } = makeClient(1);
    const promise = client.call("cache.download");

    await new Promise((resolve) => setTimeout(resolve, 5));
    stdout.write('{"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n');

    await expect(promise).resolves.toEqual({ ok: true });
  });
});
