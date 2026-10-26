import { useCallback, useEffect, useRef, useState } from 'react'

// Load data now and then every `ms` milliseconds. `deps` re-trigger a load (e.g. filters).
export function usePolling(fn, ms = 0, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const fnRef = useRef(fn)
  fnRef.current = fn

  const load = useCallback(async () => {
    try {
      const data = await fnRef.current()
      setState({ data, error: null, loading: false })
    } catch (e) {
      setState((s) => ({ ...s, error: e.message, loading: false }))
    }
  }, [])

  useEffect(() => {
    load()
    if (!ms) return undefined
    const id = setInterval(load, ms)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ms, ...deps])

  return { ...state, reload: load }
}
