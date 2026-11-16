/**
 * `npm publish` 前的清理：删掉工作树里的 __pycache__ / *.pyc。
 *
 * 为什么需要：package.json 的 `files` 字段优先于 .npmignore，`core/`、`lib/`、
 * `skills/` 整个目录会被收进包里——包括跑过 pytest 之后生成的 __pycache__。
 * .pyc 里带着构建机的绝对路径（`C:\Users\<用户名>\...`），会随包公开分发。
 *
 * 只删缓存，不碰源码；下一次 import 会重新生成。
 */
import { readdir, rm } from 'node:fs/promises'
import { join } from 'node:path'

const ROOT = process.cwd()
const SKIP = new Set(['node_modules', '.git'])

async function sweep(dir) {
  let removed = 0
  const entries = await readdir(dir, { withFileTypes: true })
  for (const entry of entries) {
    if (!entry.isDirectory()) continue
    if (SKIP.has(entry.name)) continue
    const full = join(dir, entry.name)
    if (entry.name === '__pycache__') {
      await rm(full, { recursive: true, force: true })
      removed += 1
      continue
    }
    removed += await sweep(full)
  }
  return removed
}

const removed = await sweep(ROOT)
if (removed > 0) {
  console.log('[clean-pycache] removed ' + String(removed) + ' __pycache__ director' + (removed === 1 ? 'y' : 'ies'))
} else {
  console.log('[clean-pycache] nothing to clean')
}
