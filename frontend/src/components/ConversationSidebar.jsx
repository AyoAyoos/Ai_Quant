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
import { fetchConversations, createConversation, updateConversation, deleteConversation, archiveConversation, restoreConversation } from '../lib/api.js'
import { showToast } from '../lib/toast.js'

const ICON_SIZE = 16

function ConversationItem({ conversation, isActive, onSelect, onRename, onArchive, onDelete, onRestore, editingConversationId, editName, setEditName }) {
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
        <span className="conversation-title">{conversation.title}</span>
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

  // Handle new conversation
  const handleNewConversation = useCallback(async () => {
    try {
      const data = await createConversation({})
      showToast('New conversation started')
      await loadData()
      onConversationSelect(data.id)
      navigate(`/studio?conversation=${data.id}`)
    } catch (err) {
      showToast('Failed to create conversation: ' + err.message)
    }
  }, [loadData, onConversationSelect, navigate])

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

  // Filter conversations by search query
  const filterConversations = useCallback((convs) => {
    if (!searchQuery.trim()) return convs
    const query = searchQuery.toLowerCase()
    return convs.filter(c => c.title.toLowerCase().includes(query))
  }, [searchQuery])

  // Sort conversations by updated_at descending (latest first)
  const sortedConversations = useMemo(() => {
    return [...filterConversations(conversations)].sort((a, b) => {
      const dateA = new Date(a.updated_at || a.created_at).getTime()
      const dateB = new Date(b.updated_at || b.created_at).getTime()
      return dateB - dateA
    })
  }, [conversations, filterConversations])

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
          {sortedConversations.map(conv => (
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
            />
          ))}
          {sortedConversations.length === 0 && (
            <div className="conversations-empty">
              <p>No conversations yet. Click "New Chat" to start one.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}