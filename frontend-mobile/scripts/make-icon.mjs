// scripts/make-icon.mjs
// 把 src-tauri/icons/source.svg 渲染成 1024x1024 PNG,作为 tauri icon 的输入
import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import sharp from 'sharp'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '..')
const svgPath = resolve(root, 'src-tauri/icons/source.svg')
const pngPath = resolve(root, 'src-tauri/icons/icon.png')

const svg = readFileSync(svgPath)
await sharp(svg, { density: 384 })
  .resize(1024, 1024)
  .png({ compressionLevel: 9 })
  .toFile(pngPath)
console.log('✓ 写入 1024x1024 PNG →', pngPath)
