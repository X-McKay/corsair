// Corsair-written control and security tests for CVE-2020-15123 (codecov-node), placed at test/corsair.test.js.
var fs = require('fs')
var os = require('os')
var path = require('path')
var codecov = require('../lib/codecov')

// Only the gcov step runs: no CI detection, no report search, and `dump` never uploads. Both commits pass every
// gcov option through `sanitizeVar`, which throws on a missing one, so `gcov-exec` and `gcov-args` are given.
var OPTIONS = { dump: true, disable: 'detect,search', token: 'corsair', 'gcov-exec': 'gcov', 'gcov-args': '' }

function scratch() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'corsair-'))
}

test('corsair_control', function() {
  var root = scratch()
  var result = codecov.upload({ options: Object.assign({ 'gcov-root': root }, OPTIONS) })
  expect(result.query.token).toBe('corsair')
  expect(result.files).toEqual([])
  expect(result.debug.join('\n')).toContain(root)
})

test('corsair_security', function() {
  var marker = path.join(scratch(), 'injected')
  var root = scratch() + '; touch ' + marker + '; true'
  codecov.upload({ options: Object.assign({ 'gcov-root': root }, OPTIONS) })
  expect(fs.existsSync(marker)).toBe(false)
})
