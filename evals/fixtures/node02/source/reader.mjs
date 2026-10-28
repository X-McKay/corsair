import { readFile } from "node:fs/promises";
import { relative, resolve } from "node:path";

export async function read(baseRoot, payload) {
  const root = resolve(baseRoot);
  const candidate = resolve(root, payload);
  if (relative(root, candidate).startsWith("..")) {
    return "blocked";
  }
  return readFile(candidate, "utf8");
}
