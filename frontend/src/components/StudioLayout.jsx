import { useState, useCallback, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import ConversationSidebar from './ConversationSidebar.jsx'
import ChatPage from '../pages/ChatPage.jsx'

export default function StudioLayout() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [activeConversationId, setActiveConversationId] = useState(() => 
    searchParams.get('conversation')
  )
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [conversationCount, setConversationCount] = useState(0)

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
          onClose={() => setSidebarOpen(false)}
          onCountChange={setConversationCount}
          isLoading={false}
        />
      </div>

      <div className="studio-layout__main">
        <ChatPage
          activeConversationId={activeConversationId}
          onNewChat={handleNewChat}
          isSidebarOpen={sidebarOpen}
          onSidebarToggle={() => setSidebarOpen((open) => !open)}
          conversationCount={conversationCount}
        />
      </div>

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