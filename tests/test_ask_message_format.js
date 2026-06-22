/**
 * Node smoke tests for Ask? message fence parsing.
 * Run: node tests/test_ask_message_format.js
 */
"use strict";

var fs = require("fs");
var path = require("path");
var vm = require("vm");

var window = {};
var context = {
  window: window,
  escapeHtml: function (str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  },
  console: console,
};

vm.runInContext(
  fs.readFileSync(path.join(__dirname, "../app/static/js/modules/askMessageFormat.js"), "utf8"),
  vm.createContext(context),
);

var split = window._askSplitMessageParts;
if (typeof split !== "function") {
  console.error("splitMessageParts not exported");
  process.exit(1);
}

function assert(cond, msg) {
  if (!cond) {
    console.error("FAIL:", msg);
    process.exit(1);
  }
}

var standard =
  "Here is an example:\n```java\nfor (int i = 0; i < 3; i++) {\n  System.out.println(i);\n}\n```\nDone.";
var parts = split(standard, false);
assert(parts.length === 3, "standard: three parts");
assert(parts[1].type === "code" && parts[1].lang === "java", "standard: java block");
assert(parts[1].text.indexOf("for (int") >= 0, "standard: code body");

var noClose = "```java\nfor (int i = 0; i < 3; i++) {\n  System.out.println(i);\n}";
parts = split(noClose, false);
assert(parts.length === 1 && parts[0].type === "code", "no close fence still code");
assert(parts[0].lang === "java", "no close: lang");

var inline = "```java int x = 1; ```";
parts = split(inline, false);
assert(parts.length === 1 && parts[0].type === "code", "inline fence");
assert(parts[0].text.indexOf("int x") >= 0, "inline code body");

var headerComment = "```java // Simple loop\nfor (int i = 0; i < 3; i++) {}\n```";
parts = split(headerComment, false);
assert(parts[0].lang === "java", "header comment lang");
assert(parts[0].text.indexOf("for (int") >= 0, "header comment code");

var html = window.formatAskMessageHtml(standard, {});
assert(html.indexOf("ask-code-block") >= 0, "html contains code block");
assert(html.indexOf("```") < 0, "html hides raw fences");

console.log("OK ask message format tests passed");
