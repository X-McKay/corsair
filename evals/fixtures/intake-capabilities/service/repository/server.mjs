import express from "express";
import { readFileSync } from "node:fs";
const app = express();
app.get("/read", (req, res) => res.send(readFileSync(req.query.path)));
app.listen(3000);
