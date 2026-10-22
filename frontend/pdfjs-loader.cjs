/**
 * pdfjs-dist ships its own webpack runtime (`__webpack_require__`, `__webpack_exports__`). When Next's
 * webpack bundles that file it treats those names as its own module API and rewrites them, which
 * breaks pdf.js at load time ("Object.defineProperty called on non-object"). Renaming the
 * identifiers keeps the embedded runtime self-contained.
 */
module.exports = function pdfjsLoader(source) {
  return source.replace(/__webpack_require__/g, "__pdfjs_require__").replace(/__webpack_exports__/g, "__pdfjs_exports__");
};
