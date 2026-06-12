/**
 * Top-level error boundary — keeps a crash in one route from
 * blanking the whole app. Critical for an emergency-information PWA.
 */
import React from 'react'

interface State { hasError: boolean }

export default class ErrorBoundary extends React.Component<React.PropsWithChildren, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  handleReload = () => {
    window.location.reload()
  }

  render() {
    if (!this.state.hasError) return this.props.children

    return (
      <div style={{
        minHeight: '100dvh', display: 'flex', alignItems: 'center',
        justifyContent: 'center', padding: 24, background: '#F6F7F9',
        fontFamily: "'Public Sans Variable', 'Segoe UI', system-ui, sans-serif",
      }}>
        <div role="alert" style={{
          maxWidth: 420, background: '#fff', border: '1px solid #D9DEE5',
          borderRadius: 10, padding: '28px 24px', textAlign: 'center',
        }}>
          <h1 style={{ fontSize: '1.1rem', marginBottom: 8, color: '#1A2332' }}>
            Something went wrong
          </h1>
          <p style={{ fontSize: '0.85rem', color: '#5C6878', marginBottom: 20, lineHeight: 1.5 }}>
            The page failed to load. Your alerts are still available —
            reload to continue, or dial *384*FLOOD# on any phone.
          </p>
          <button
            onClick={this.handleReload}
            style={{
              background: '#205493', color: '#fff', border: '1px solid #163E6F',
              borderRadius: 8, padding: '10px 24px', fontSize: '0.85rem',
              fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
            }}
          >
            Reload
          </button>
        </div>
      </div>
    )
  }
}
