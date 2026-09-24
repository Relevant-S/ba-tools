# The frame inventory — generated, never hand-written

A list of every page and every top-level frame in a design file, with node ids. Useful for finding a
sibling to clone and for linking clarification pages. It is **generated from the live file** and saved
to the profile's `inventory` path. Never edit it by hand, and never keep it inside a config file —
a hand-kept list goes stale and makes every build load thousands of lines.

**Regenerate** when a build cannot find a page or frame, or before linking screens on a clarification
page. One `use_figma` call on the design file:

```js
const out = [];
for (const page of figma.root.children) {          // figma.root.children lists EVERY page;
  await page.loadAsync();                           // get_metadata without a node id misses some
  out.push({ page: page.name, id: page.id,
    frames: page.children
      .filter(n => ['FRAME', 'SECTION', 'COMPONENT', 'COMPONENT_SET'].includes(n.type))
      .map(n => ({ name: n.name, id: n.id, type: n.type,
        children: n.type === 'SECTION'
          ? n.children.filter(c => c.type === 'FRAME').map(c => ({ name: c.name, id: c.id })) : undefined })) });
}
return out;
```

Write the result as markdown: one `##` per page (name + id), one line per frame (name + id), Section
children indented under their Section. Put the date and file key at the top. Commit it with the build.
