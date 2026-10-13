import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const root = process.cwd()
const manifest = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'))
const expected = { ...manifest.dependencies, ...manifest.devDependencies }
const missing = []

for (const [name, version] of Object.entries(expected)) {
  let installed = ''
  try {
    installed = JSON.parse(readFileSync(join(root, 'node_modules', name, 'package.json'), 'utf8')).version
  } catch {
    missing.push(name)
    continue
  }
  if (installed !== version) missing.push(`${name} (需要 ${version}，已安装 ${installed})`)
}

if (missing.length) {
  console.error(`前端依赖缺失或版本不符：\n${missing.join('\n')}`)
  process.exit(1)
}
