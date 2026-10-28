import { readFile } from "node:fs/promises";

export async function read(baseRoot, payload) {
  return readFile(`${baseRoot}/${payload}`, "utf8");
}
