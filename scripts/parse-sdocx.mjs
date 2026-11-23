// Export only the geometry needed by the local Markdown converter.
import { readFile, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

function strokesIn(value, result = [], sourceOffset = null) {
  if (!value || typeof value !== 'object') return result;
  if ('source_offset' in value) sourceOffset = value.source_offset;
  if (Array.isArray(value.points) && 'pen_width' in value) {
    result.push({ ...value, sourceOffset });
  } else {
    for (const child of Object.values(value)) strokesIn(child, result, sourceOffset);
  }
  return result;
}

const [input, output] = process.argv.slice(2);
if (!input || !output) {
  console.error('Usage: node scripts/parse-sdocx.mjs input.sdocx output.json');
  process.exit(2);
}
let session;
try {
  const moduleUrl = import.meta.resolve('@twango/sdocx');
  const sdk = await import(moduleUrl);
  await sdk.default({ module_or_path: await readFile(join(dirname(fileURLToPath(moduleUrl)), 'sdocx_bg.wasm')) });
  session = new sdk.DocumentSession(new Uint8Array(await readFile(input)));
  const inspection = session.inspection();
  const pages = inspection.layout?.pages;
  if (!Array.isArray(pages)) throw new Error('Unsupported parser schema: layout.pages is missing');
  const result = {
    parser: '@twango/sdocx',
    diagnostics: inspection.report?.diagnostics ?? [],
    pages: pages.map((entry, i) => {
      const page = entry.page;
      function ownerPageWidth(stroke) {
        const mask = stroke.rendering?.metadata?.field_mask;
        // Owner page size is common flexible field 14. Ask the upstream
        // decoder to read it; do not assume dimensions from a byte suffix.
        if (!mask || !(mask[1] & 64)) return null;
        if (stroke.sourceOffset == null) throw new Error('Stroke owner size is declared but its source offset is missing');
        const detail = JSON.parse(session.debug(JSON.stringify({
          kind: 'object', page: entry.source_page_index, offset: stroke.sourceOffset,
        })));
        const width = detail.flexible?.owner_page_size?.width;
        if (!(width > 0) || !Number.isFinite(width)) {
          throw new Error('Cannot decode stroke owner page width; refusing to guess its position');
        }
        return width;
      }
      return {
        number: i + 1, uuid: page.uuid, width: page.width, height: page.height,
        pdf_placements: page.background?.pdf_paper ?? [],
        strokes: strokesIn(page.objects).map((stroke, j) => ({
          id: j + 1, points: stroke.points, bbox: stroke.bbox,
          color: stroke.color, width: stroke.pen_width,
          pen: stroke.rendering?.pen_name ?? '',
          owner_page_width: ownerPageWidth(stroke),
          visible: stroke.rendering?.metadata?.visible !== false,
          eraser: stroke.rendering?.properties?.eraser === true,
        })),
      };
    }),
  };
  await writeFile(output, JSON.stringify(result));
} catch (error) {
  console.error(`Parser failed: ${error.message}`);
  process.exitCode = 1;
} finally {
  session?.dispose();
  session?.free?.();
}
