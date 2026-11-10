import { useState, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Plus,
  MessageSquare,
  Archive,
  Trash2,
  Edit2,
  Loader2,
} from 'lucide-react'
import { fetchConversations, updateConversation, deleteConversation, archiveConversation, restoreConversation, fetchConversation } from '../lib/api.js'
import { showToast } from '../lib/toast.js'

const ICON_SIZE = 16

// Placeholder titles that should be replaced with generated titles
const PLACEHOLDER_TITLES = new Set([
  'New conversation',
  'New Conversation',
  'New chat',
  'New Chat',
])

function generateTitleFromFirstMessage(messages) {
  const firstUserMessage = messages?.find(m => m.role === 'user')
  if (!firstUserMessage?.content) return null
  // Take first 50 characters of the first user message
  const content = firstUserMessage.content.trim()
  return content.length > 50 ? content.slice(0, 50) + '…' : content
}

function formatRelativeTime(dateString) {
  if (!dateString) return ''
  const date = new Date(dateString)
  if (isNaN(date.getTime())) return ''
  const now = new Date()
  const diffMs = now - date
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)
  
  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`
  
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function ConversationItem({ conversation, isActive, onSelect, onRename, onArchive, onDelete, onRestore, editingConversationId, editName, setEditName, displayTitle, relativeTime }) {
  const isEditing = editingConversationId === conversation.id
  const isArchived = conversation.status === 'archived'

  if (isEditing) {
    return (
      <div className="conversation-item conversation-item--editing">
        <input
          type="text"
          value={editName}
          onChange={(e) => setEditName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && editName.trim()) {
              onRename(conversation.id, editName.trim())
            } else if (e.key === 'Escape') {
              onRename(conversation.id, conversation.title)
            }
          }}
          onBlur={() => onRename(conversation.id, editName.trim() || conversation.title)}
          autoFocus
          className="conversation-edit-input"
        />
      </div>
    )
  }

  return (
    <div className={`conversation-item${isActive ? ' conversation-item--active' : ''}${isArchived ? ' conversation-item--archived' : ''}`}>
      <button
        className="conversation-main"
        onClick={() => onSelect(conversation.id)}
        title={conversation.title}
      >
        <MessageSquare className="conversation-icon" size={ICON_SIZE} />
        <div className="conversation-title-container">
          <span className="conversation-title">{displayTitle}</span>
          {relativeTime && <span className="conversation-timestamp">{relativeTime}</span>}
        </div>
        {conversation.message_count > 0 && (
          <span className="conversation-message-count">{conversation.message_count}</span>
        )}
      </button>
      <div className="conversation-menu">
        <button
          className="conversation-menu-btn"
          onClick={(e) => { e.stopPropagation(); onRename(conversation.id, conversation.title); }}
          title="Rename"
          aria-label="Rename conversation"
        >
          <Edit2 size={ICON_SIZE} />
        </button>
        {isArchived ? (
          <button
            className="conversation-menu-btn"
            onClick={(e) => { e.stopPropagation(); onRestore(conversation.id); }}
            title="Restore"
            aria-label="Restore conversation"
          >
            <Archive size={ICON_SIZE} />
          </button>
        ) : (
          <button
            className="conversation-menu-btn"
            onClick={(e) => { e.stopPropagation(); onArchive(conversation.id); }}
            title="Archive"
            aria-label="Archive conversation"
          >
            <Archive size={ICON_SIZE} />
          </button>
        )}
        <button
          className="conversation-menu-btn conversation-menu-btn--danger"
          onClick={(e) => { e.stopPropagation(); onDelete(conversation.id); }}
          title="Delete"
          aria-label="Delete conversation"
        >
          <Trash2 size={ICON_SIZE} />
        </button>
      </div>
    </div>
  )
}

export default function ConversationSidebar({
  activeConversationId,
  onConversationSelect,
  onNewChat: _onNewChat,
  isLoading: _isLoading,
}) {
  const navigate = useNavigate()
  const [conversations, setConversations] = useState([])
  const [loading, setLoading] = useState(true)
  const [editingConversationId, setEditingConversationId] = useState(null)
  const [editConversationName, setEditConversationName] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [enrichedConversations, setEnrichedConversations] = useState({})

  // Load conversations
  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      const conversationsData = await fetchConversations()
      setConversations(conversationsData)
    } catch (err) {
      showToast('Failed to load conversations: ' + err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  // Enrich conversations with generated titles and timestamps
  useEffect(() => {
    if (conversations.length === 0) {
      setEnrichedConversations({})
      return
    }

    let cancelled = false

    const enrichConversations = async () => {
      const enriched = {}
      
      for (const conv of conversations) {
        if (cancelled) break
        
        let displayTitle = conv.title
        let relativeTime = conv.updated_at ? formatRelativeTime(conv.updated_at) : ''
        
        // Check if title is a placeholder that should be replaced
        const isPlaceholder = PLACEHOLDER_TITLES.has(conv.title) || 
                              conv.title === 'New conversation' ||
                              conv.title.trim() === ''
        
        if (isPlaceholder && conv.message_count > 0) {
          try {
            // Fetch full conversation to get first user message
            const fullConv = await fetchConversation(conv.id)
            const generatedTitle = generateTitleFromFirstMessage(fullConv.messages)
            if (generatedTitle) {
              displayTitle = generatedTitle
            }
          } catch (err) {
            // Silently fail, keep original title
            console.debug('Failed to enrich conversation title:', err)
          }
        }
        
        if (!cancelled) {
          enriched[conv.id] = { displayTitle, relativeTime }
        }
      }
      
      if (!cancelled) {
        setEnrichedConversations(enriched)
      }
    }

    enrichConversations()
    return () => { cancelled = true }
  }, [conversations])

  // Handle new conversation - just reset state, don't create a conversation yet
  // Conversation will be created on first message via postChat
  const handleNewConversation = useCallback(() => {
    onConversationSelect(null)
    navigate('/studio', { replace: true })
    showToast('New chat started')
  }, [onConversationSelect, navigate])

  // Handle conversation rename
  const handleRenameConversation = useCallback(async (conversationId, newName) => {
    if (!newName.trim() || newName.trim() === conversations.find(c => c.id === conversationId)?.title) {
      setEditingConversationId(null)
      return
    }
    try {
      await updateConversation(conversationId, { title: newName.trim() })
      showToast('Conversation renamed')
      await loadData()
    } catch (err) {
      showToast('Failed to rename conversation: ' + err.message)
    }
    setEditingConversationId(null)
  }, [conversations, loadData])

  // Handle conversation archive
  const handleArchiveConversation = useCallback(async (conversationId) => {
    try {
      await archiveConversation(conversationId)
      showToast('Conversation archived')
      await loadData()
    } catch (err) {
      showToast('Failed to archive conversation: ' + err.message)
    }
  }, [loadData])

  // Handle conversation restore
  const handleRestoreConversation = useCallback(async (conversationId) => {
    try {
      await restoreConversation(conversationId)
      showToast('Conversation restored')
      await loadData()
    } catch (err) {
      showToast('Failed to restore conversation: ' + err.message)
    }
  }, [loadData])

  // Handle conversation delete
  const handleDeleteConversation = useCallback(async (conversationId) => {
    if (!window.confirm('Delete this conversation permanently?')) return
    try {
      await deleteConversation(conversationId)
      showToast('Conversation deleted')
      await loadData()
    } catch (err) {
      showToast('Failed to delete conversation: ' + err.message)
    }
  }, [loadData])

  // Filter and sort: only active conversations, sorted by updated_at descending
  const filteredAndSortedConversations = useMemo(() => {
    let filtered = [...conversations]
      .filter(c => c.status !== 'archived') // Only show active conversations
      .filter(c => c.message_count > 0) // Only show conversations with at least one message

    // Apply search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase()
      filtered = filtered.filter(c => c.title.toLowerCase().includes(query))
    }

    return filtered.sort((a, b) => {
      const dateA = new Date(a.updated_at || a.created_at).getTime()
      const dateB = new Date(b.updated_at || b.created_at).getTime()
      return dateB - dateA
    })
  }, [conversations, searchQuery])

  if (loading) {
    return (
      <div className="conversation-sidebar loading">
        <div className="sidebar-header">
          <h2>Conversations</h2>
        </div>
        <div className="sidebar-loading">
          <Loader2 size={24} className="spinner" />
        </div>
      </div>
    )
  }

  return (
    <div className="conversation-sidebar">
      <div className="sidebar-header">
        <h2>Conversations</h2>
        <div className="sidebar-header-actions">
          <input
            type="text"
            placeholder="Search conversations..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="sidebar-search"
            aria-label="Search conversations"
          />
        </div>
      </div>

      <div className="sidebar-actions">
        <button
          className="btn btn--primary btn--icon-text"
          onClick={handleNewConversation}
        >
          <Plus size={ICON_SIZE} />
          <span>New Chat</span>
        </button>
      </div>

      {/* Conversations List */}
      <div className="sidebar-section">
        <div className="sidebar-section-header">
          <h3>Recent Conversations</h3>
        </div>
        <div className="conversation-list">
          {filteredAndSortedConversations.map(conv => {
            const enriched = enrichedConversations[conv.id] || {}
            return (
              <ConversationItem
                key={conv.id}
                conversation={conv}
                isActive={activeConversationId === conv.id}
                onSelect={onConversationSelect}
                onRename={(id, name) => {
                  const currentConv = conversations.find(c => c.id === id)
                  if (currentConv && name.trim() !== currentConv.title) {
                    // Confirming edit with a new name
                    handleRenameConversation(id, name)
                  } else {
                    // Starting edit mode or cancelling
                    setEditingConversationId(id)
                    setEditConversationName(name)
                  }
                }}
                onArchive={handleArchiveConversation}
                onDelete={handleDeleteConversation}
                onRestore={handleRestoreConversation}
                editingConversationId={editingConversationId}
                editName={editConversationName}
                setEditName={setEditConversationName}
                displayTitle={enriched.displayTitle || conv.title}
                relativeTime={enriched.relativeTime}
              />
            )
          })}
          {filteredAndSortedConversations.length === 0 && (
            <div className="conversations-empty">
              <p>No conversations yet. Click "New Chat" to start one.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}