#!/usr/bin/env node
/**
 * Generates src/api/openapi-types.ts from docs/openapi-snapshot.json.
 *
 * Every API response and request body on the wire is camelCase — DRF's
 * CamelCaseJSONRenderer/CamelCaseJSONParser (backend/core/renderers.py,
 * backend/config/settings.py) camelize/underscoreize object keys in both
 * directions. drf-spectacular has no knowledge of that renderer, so the raw
 * schema (and a plain `openapi-typescript` run) describes the snake_case
 * serializer field names instead. This script camelizes every property name
 * under components.schemas before handing the schema to openapi-typescript,
 * so the generated types describe the JSON shape the app actually sees.
 *
 * Query/path parameters are left untouched: djangorestframework-camel-case
 * only rewrites body payloads, not query strings (see the manual snake_case
 * params built in src/api/statutory.ts), and parameter schemas here live
 * outside components.schemas, so they're never visited by camelizeSchema.
 */
import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { load as loadYaml } from 'js-yaml';
import openapiTS, { astToString, COMMENT_HEADER } from 'openapi-typescript';

const here = path.dirname(fileURLToPath(import.meta.url));
const SNAPSHOT_PATH = path.resolve(here, '../../docs/openapi-snapshot.json');
const OUTPUT_PATH = path.resolve(here, '../src/api/openapi-types.ts');

// Ports djangorestframework_camel_case.util.camelize's key transform exactly
// (camelize_re / underscore_to_camel), so field names match runtime byte-for-byte.
const CAMELIZE_RE = /[a-z0-9]?_[a-z0-9]/g;

function camelizeKey(key) {
  if (typeof key !== 'string' || !key.includes('_')) return key;
  return key.replace(CAMELIZE_RE, (match) =>
    match.length === 3 ? match[0] + match[2].toUpperCase() : match[1].toUpperCase(),
  );
}

function camelizeSchema(node, seen = new Set()) {
  if (node === null || typeof node !== 'object' || seen.has(node)) return;
  seen.add(node);

  if (Array.isArray(node)) {
    for (const item of node) camelizeSchema(item, seen);
    return;
  }

  if (node.properties && typeof node.properties === 'object') {
    const renamed = {};
    for (const [key, value] of Object.entries(node.properties)) {
      const newKey = camelizeKey(key);
      if (Object.prototype.hasOwnProperty.call(renamed, newKey)) {
        throw new Error(`camelCase collision on property "${key}" -> "${newKey}"`);
      }
      renamed[newKey] = value;
      camelizeSchema(value, seen);
    }
    node.properties = renamed;
  }

  if (Array.isArray(node.required)) {
    node.required = node.required.map(camelizeKey);
  }

  for (const key of ['items', 'additionalProperties']) {
    if (node[key] && typeof node[key] === 'object') camelizeSchema(node[key], seen);
  }
  for (const key of ['allOf', 'oneOf', 'anyOf']) {
    if (Array.isArray(node[key])) {
      for (const sub of node[key]) camelizeSchema(sub, seen);
    }
  }
}

const schema = loadYaml(readFileSync(SNAPSHOT_PATH, 'utf-8'));

for (const name of Object.keys(schema.components?.schemas ?? {})) {
  camelizeSchema(schema.components.schemas[name]);
}

const ast = await openapiTS(schema);
writeFileSync(OUTPUT_PATH, COMMENT_HEADER + astToString(ast));
console.log(`Wrote ${path.relative(process.cwd(), OUTPUT_PATH)}`);
