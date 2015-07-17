# Universal sourcemap tool

You can concatenate and cascade sourcemaps.
Even with raw code snippets without sourcemaps!

For instance, we have two javascript files with sourcemaps:
- **a.js**
- **a.map**
- **b.js**
- **b.map**

We can join them into one:

```
sourcemap_tool.py concat \
  --file a.js \
  --file b.js \
  --outfile concat.js --outmap concat.map
```

We can even concat with raw javascript code without sourcemaps:

```
echo ';(function(){' > open.js
echo '})();' > close.js
sourcemap_tool.py concat \
  --file open.js \
  --file a.js \
  --file b.js \
  --file close.js \
  --outfile concat.js --outmap concat.map
```

Finally we want to compress the code:

```
closure-compiler --charset UTF-8 -O SIMPLE \
  --js concat.js \
  --create_source_map closure.map \
  --js_output_file result.js
sourcemap_tool.py cascade \
  concat.map \
  closure.map \
  result.js.map \
  --fixmapurl result.js
```

**result.js.map** will map to your original sources!
