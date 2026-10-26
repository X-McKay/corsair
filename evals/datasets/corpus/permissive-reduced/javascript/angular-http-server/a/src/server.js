'use strict';
// Reduced from angular-http-server.js (simonh1000/angular-http-server): the static-file
// request handler and its URL->path resolution, extracted to a minimal http module so it
// runs offline. Application logic only; no test or attack code.
const http = require('http');
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..', 'public');

function resolveUrl(filename) {
  const normalizedName = path.normalize(filename).replace(/^(\.\.[\/\\])+/, '');
  return path.join(ROOT, normalizedName);
}

function requestListener(req, res) {
  const url = req.url.split('?')[0];
  const possibleFilename = resolveUrl(url.slice(1)) || 'dummy';
  fs.stat(possibleFilename, function (err, stats) {
    if (!err && stats.isFile()) {
      const fileBuffer = fs.readFileSync(possibleFilename);
      res.end(fileBuffer);
    } else {
      res.statusCode = 404;
      res.end('not found');
    }
  });
}

function createServer() {
  return http.createServer(requestListener);
}

module.exports = { requestListener, createServer, resolveUrl, ROOT };
