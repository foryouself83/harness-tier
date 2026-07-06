# Static Performance Anti-Pattern Catalog — React (Frontend Re-renders)

> SSOT: based on the §10.4 preliminary research from the spec (2026-06). Source URLs and licenses are cited.

---

## 1. Detect Whether React Compiler v1.0 Is Active (as of the 2025-10 GA)

**Detect first** — check for `babel-plugin-react-compiler` / `@babel/plugin-react-compiler` / the Vite
`reactCompiler` option (camelCase, no hyphen — a plain `react-compiler` string match misses this):

```bash
grep -riE "react-compiler|babel-plugin-react-compiler|reactCompiler" package.json babel.config.* vite.config.* 2>/dev/null
```

| State | Applicable rule |
|---|---|
| **Compiler active** | Relax the manual `memo`/`useMemo`/`useCallback` rules. Instead, focus checks on **Rules of React violations** (`eslint-plugin-react-hooks`). |
| **Compiler inactive** | Statically detect inline object/function props, missing `useCallback`, unnecessary `React.createElement` re-creation, etc. |

## 2. When React Compiler Is Active

- The `rules-of-hooks` + `exhaustive-deps` rules of `eslint-plugin-react-hooks` (integrated with the Compiler)
- Rules of React violations such as calling hooks outside a component or calling hooks conditionally

| Item | Source |
|---|---|
| eslint-plugin-react-hooks (MIT) | https://react.dev/reference/eslint-plugin-react-hooks |
| React Compiler v1.0 blog | https://react.dev/blog/2025/10/07/react-compiler-1 |
| React Compiler introduction | https://react.dev/learn/react-compiler/introduction |

## 3. When React Compiler Is Inactive

| Static detection pattern | Problem | Recommendation | Source |
|---|---|---|---|
| Inline object in a JSX prop `<Comp style={{ color: 'red' }}>` | A new object reference every render → child re-renders | Memoize with `useMemo` or extract to a module constant | https://react.dev/reference/react/useMemo |
| Inline function in a JSX prop `<Comp onClick={() => handler(id)}>` | A new function reference every render | `useCallback(…, [id])` | https://react.dev/reference/react/useCallback |
| Inline prop on a `React.memo`-wrapped component | The memo is invalidated | Give the prop a stable reference | https://react.dev/reference/react/memo |
| Missing or excessive `useEffect` deps array | Stale closure / infinite loop | Apply the `exhaustive-deps` lint rule | https://react.dev/reference/eslint-plugin-react-hooks |

## 4. Runtime Re-render Tools (verification delegated)

| Tool | License | Source |
|---|---|---|
| React DevTools Profiler | MIT | https://react.dev/reference/react/Profiler |
| why-did-you-render | MIT | https://github.com/welldone-software/why-did-you-render |
| react-scan | MIT | https://github.com/aidenybai/react-scan |
