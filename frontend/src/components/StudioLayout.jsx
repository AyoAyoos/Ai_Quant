import { useState, useCallback, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import ConversationSidebar from './ConversationSidebar.jsx'
import ChatPage from '../pages/ChatPage.jsx'

export default function StudioLayout() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [activeConversationId, setActiveConversationId] = useState(() => 
    searchParams.get('conversation')
  )
  const [sidebarOpen, setSidebarOpen] = useState(true)

  // Sync URL with active conversation
  useEffect(() => {
    const urlConvId = searchParams.get('conversation')
    if (urlConvId !== activeConversationId) {
      setActiveConversationId(urlConvId)
    }
  }, [searchParams, activeConversationId])

  const handleConversationSelect = useCallback((conversationId) => {
    setActiveConversationId(conversationId)
    setSearchParams({ conversation: conversationId }, { replace: true })
    setSidebarOpen(false) // Close sidebar on mobile after selection
  }, [setSearchParams])

  const handleNewChat = useCallback(() => {
    // Clear conversation ID to start a new chat
    setActiveConversationId(null)
    setSearchParams({}, { replace: true })
  }, [setSearchParams])

  return (
    <div className="studio-layout" data-sidebar-open={sidebarOpen}>
      <div className="studio-layout__sidebar">
        <ConversationSidebar
          activeConversationId={activeConversationId}
          onConversationSelect={handleConversationSelect}
          onNewChat={handleNewChat}
          isLoading={false}
        />
      </div>

      <div className="studio-layout__main">
        <ChatPage
          activeConversationId={activeConversationId}
          onNewChat={handleNewChat}
          isSidebarOpen={sidebarOpen}
          onSidebarToggle={() => setSidebarOpen(!sidebarOpen)}
        />
      </div>

      {/* Mobile sidebar toggle button */}
      <button
        className="studio-layout__mobile-toggle"
        onClick={() => setSidebarOpen(!sidebarOpen)}
        aria-label={sidebarOpen ? 'Close conversation history' : 'Open conversation history'}
        aria-expanded={sidebarOpen}
      >
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div 
          className="studio-layout__overlay" 
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}
    </div>
  )
}