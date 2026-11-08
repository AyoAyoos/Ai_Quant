import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Plus,
  MessageSquare,
  Search,
  MoreHorizontal,
  Archive,
  Trash2,
  Edit2,
  FolderPlus,
  Folder,
  ChevronRight,
  ChevronDown,
  X,
  Loader2,
} from 'lucide-react'
import { fetchProjects, createProject, updateProject, deleteProject } from '../lib/api.js'
import { fetchConversations, createConversation, updateConversation, deleteConversation, archiveConversation, restoreConversation, moveConversation } from '../lib/api.js'
import { showToast } from '../lib/toast.js'

const ICON_SIZE = 16

function ProjectItem({ project, isOpen, onToggle, onSelect, onRename, onDelete, editingProjectId, editName, setEditName }) {
  const isEditing = editingProjectId === project.id

  if (isEditing) {
    return (
      <div className="project-item project-item--editing">
        <input
          type="text"
          value={editName}
          onChange={(e) => setEditName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && editName.trim()) {
              onRename(project.id, editName.trim())
            } else if (e.key === 'Escape') {
              onRename(project.id, project.name)
            }
          }}
          onBlur={() => onRename(project.id, editName.trim() || project.name)}
          autoFocus
          className="project-edit-input"
        />
      </div>
    )
  }

  return (
    <div className="project-item">
      <div
        className={`project-header${isOpen ? ' project-header--open' : ''}`}
        onClick={onToggle}
      >
        <Folder className="project-icon" size={ICON_SIZE} />
        <span className="project-name" title={project.name}>{project.name}</span>
        <div className="project-actions">
          <button
            className="project-action-btn"
            onClick={(e) => { e.stopPropagation(); onRename(project.id, project.name); }}
            title="Rename"
            aria-label="Rename project"
          >
            <Edit2 size={ICON_SIZE} />
          </button>
          <button
            className="project-action-btn"
            onClick={(e) => { e.stopPropagation(); onDelete(project.id); }}
            title="Delete"
            aria-label="Delete project"
          >
            <Trash2 size={ICON_SIZE} />
          </button>
        </div>
      </div>
    </div>
  )
}

function ConversationItem({ conversation, isActive, onSelect, onRename, onMove, onArchive, onDelete, onRestore, editingConversationId, editName, setEditName }) {
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
          onClick={(e) => { e.stopPropagation(); onMove(conversation.id); }}
          title="Move to project"
          aria-label="Move to project"
        >
          <Folder size={ICON_SIZE} />
        </button>
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
  onNewChat,
  isLoading,
}) {
  const navigate = useNavigate()
  const [projects, setProjects] = useState([])
  const [conversations, setConversations] = useState([])
  const [openProjects, setOpenProjects] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showNewProjectModal, setShowNewProjectModal] = useState(false)
  const [newProjectName, setNewProjectName] = useState('')
  const [newProjectDescription, setNewProjectDescription] = useState('')
  const [creatingProject, setCreatingProject] = useState(false)
  const [editingProjectId, setEditingProjectId] = useState(null)
  const [editProjectName, setEditProjectName] = useState('')
  const [editingConversationId, setEditingConversationId] = useState(null)
  const [editConversationName, setEditConversationName] = useState('')
  const [showMoveDialog, setShowMoveDialog] = useState(false)
  const [moveConversationId, setMoveConversationId] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')

  // Load projects and conversations
  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      const [projectsData, conversationsData] = await Promise.all([
        fetchProjects(),
        fetchConversations(),
      ])
      setProjects(projectsData)
      setConversations(conversationsData)
      // Auto-open projects that have conversations
      const initiallyOpen = {}
      conversationsData.forEach(c => {
        if (c.project_id) initiallyOpen[c.project_id] = true
      })
      setOpenProjects(initiallyOpen)
      setError(null)
    } catch (err) {
      setError(err.message)
      showToast('Failed to load conversations: ' + err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  // Handle new project creation
  const handleCreateProject = async () => {
    if (!newProjectName.trim()) return
    try {
      setCreatingProject(true)
      await createProject({ name: newProjectName.trim(), description: newProjectDescription.trim() || undefined })
      showToast('Project created')
      setShowNewProjectModal(false)
      setNewProjectName('')
      setNewProjectDescription('')
      await loadData()
    } catch (err) {
      showToast('Failed to create project: ' + err.message)
    } finally {
      setCreatingProject(false)
    }
  }

  // Handle project rename
  const handleRenameProject = async (projectId, newName) => {
    if (!newName.trim() || newName.trim() === projects.find(p => p.id === projectId)?.name) {
      setEditingProjectId(null)
      return
    }
    try {
      await updateProject(projectId, { name: newName.trim() })
      showToast('Project renamed')
      await loadData()
    } catch (err) {
      showToast('Failed to rename project: ' + err.message)
    }
    setEditingProjectId(null)
  }

  // Handle project delete
  const handleDeleteProject = async (projectId) => {
    if (!window.confirm('Delete this project? Conversations will be moved to "Unassigned".')) return
    try {
      await deleteProject(projectId)
      showToast('Project deleted')
      await loadData()
    } catch (err) {
      showToast('Failed to delete project: ' + err.message)
    }
  }

  // Handle conversation select
  const handleConversationSelect = (conversationId) => {
    onConversationSelect(conversationId)
    navigate(`/studio?conversation=${conversationId}`)
  }

  // Handle new conversation
  const handleNewConversation = async (projectId = null) => {
    try {
      const data = await createConversation({ project_id: projectId })
      showToast('New conversation started')
      await loadData()
      handleConversationSelect(data.id)
    } catch (err) {
      showToast('Failed to create conversation: ' + err.message)
    }
  }

  // Handle conversation rename
  const handleRenameConversation = async (conversationId, newName) => {
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
  }

  // Handle conversation archive
  const handleArchiveConversation = async (conversationId) => {
    try {
      await archiveConversation(conversationId)
      showToast('Conversation archived')
      await loadData()
    } catch (err) {
      showToast('Failed to archive conversation: ' + err.message)
    }
  }

  // Handle conversation restore
  const handleRestoreConversation = async (conversationId) => {
    try {
      await restoreConversation(conversationId)
      showToast('Conversation restored')
      await loadData()
    } catch (err) {
      showToast('Failed to restore conversation: ' + err.message)
    }
  }

  // Handle conversation delete
  const handleDeleteConversation = async (conversationId) => {
    if (!window.confirm('Delete this conversation permanently?')) return
    try {
      await deleteConversation(conversationId)
      showToast('Conversation deleted')
      await loadData()
    } catch (err) {
      showToast('Failed to delete conversation: ' + err.message)
    }
  }

  // Handle move conversation
  const handleMoveConversation = async (conversationId, targetProjectId) => {
    try {
      await moveConversation(conversationId, { projectId: targetProjectId })
      showToast('Conversation moved')
      await loadData()
    } catch (err) {
      showToast('Failed to move conversation: ' + err.message)
    }
    setShowMoveDialog(false)
    setMoveConversationId(null)
  }

  // Group conversations by project
  const conversationsByProject = {}
  const unassignedConversations = []

  conversations.forEach(conv => {
    if (conv.project_id) {
      if (!conversationsByProject[conv.project_id]) {
        conversationsByProject[conv.project_id] = []
      }
      conversationsByProject[conv.project_id].push(conv)
    } else {
      unassignedConversations.push(conv)
    }
  })

  // Filter conversations by search query
  const filterConversations = (convs) => {
    if (!searchQuery.trim()) return convs
    const query = searchQuery.toLowerCase()
    return convs.filter(c => c.title.toLowerCase().includes(query))
  }

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
          onClick={() => setShowNewProjectModal(true)}
          disabled={creatingProject}
        >
          <FolderPlus size={ICON_SIZE} />
          <span>New Project</span>
        </button>
        <button
          className="btn btn--secondary btn--icon-text"
          onClick={() => handleNewConversation()}
        >
          <MessageSquare size={ICON_SIZE} />
          <span>New Chat</span>
        </button>
      </div>

      {/* Projects Section */}
      <div className="sidebar-section">
        <div className="sidebar-section-header">
          <h3>Projects</h3>
        </div>
        <div className="project-list">
          {projects.map(project => {
            const projectConvs = filterConversations(conversationsByProject[project.id] || [])
            const isOpen = openProjects[project.id] !== false
            return (
              <div key={project.id} className="project-wrapper">
                <ProjectItem
                  project={project}
                  isOpen={isOpen}
                  onToggle={() => setOpenProjects(prev => ({ ...prev, [project.id]: !isOpen }))}
                  onRename={(id, name) => {
                    setEditingProjectId(id)
                    setEditProjectName(name)
                  }}
                  onDelete={handleDeleteProject}
                  editingProjectId={editingProjectId}
                  editName={editProjectName}
                  setEditName={setEditProjectName}
                />
                {isOpen && projectConvs.length > 0 && (
                  <div className="project-conversations">
                    {projectConvs.map(conv => (
                      <ConversationItem
                        key={conv.id}
                        conversation={conv}
                        isActive={activeConversationId === conv.id}
                        onSelect={handleConversationSelect}
                        onRename={(id, name) => {
                          setEditingConversationId(id)
                          setEditConversationName(name)
                        }}
                        onMove={(id) => {
                          setMoveConversationId(id)
                          setShowMoveDialog(true)
                        }}
                        onArchive={handleArchiveConversation}
                        onDelete={handleDeleteConversation}
                        onRestore={handleRestoreConversation}
                        editingConversationId={editingConversationId}
                        editName={editConversationName}
                        setEditName={setEditConversationName}
                      />
                    ))}
                  </div>
                )}
                {isOpen && projectConvs.length === 0 && (
                  <div className="project-empty">
                    <button
                      className="btn btn--ghost btn--sm"
                      onClick={() => handleNewConversation(project.id)}
                    >
                      <Plus size={ICON_SIZE} /> Start a chat in this project
                    </button>
                  </div>
                )}
              </div>
            )
          })}
          {projects.length === 0 && (
            <div className="projects-empty">
              <p>No projects yet. Create your first project to organize conversations.</p>
            </div>
          )}
        </div>
      </div>

      {/* Unassigned Conversations */}
      <div className="sidebar-section">
        <div className="sidebar-section-header">
          <h3>Recent Conversations</h3>
        </div>
        <div className="conversation-list">
          {filterConversations(unassignedConversations).map(conv => (
            <ConversationItem
              key={conv.id}
              conversation={conv}
              isActive={activeConversationId === conv.id}
              onSelect={handleConversationSelect}
              onRename={(id, name) => {
                setEditingConversationId(id)
                setEditConversationName(name)
              }}
              onMove={(id) => {
                setMoveConversationId(id)
                setShowMoveDialog(true)
              }}
              onArchive={handleArchiveConversation}
              onDelete={handleDeleteConversation}
              onRestore={handleRestoreConversation}
              editingConversationId={editingConversationId}
              editName={editConversationName}
              setEditName={setEditConversationName}
            />
          ))}
          {filterConversations(unassignedConversations).length === 0 && (
            <div className="conversations-empty">
              <p>No conversations yet. Click "New Chat" to start one.</p>
            </div>
          )}
        </div>
      </div>

      {/* New Project Modal */}
      {showNewProjectModal && (
        <div className="modal-overlay" onClick={() => setShowNewProjectModal(false)}>
          <div className="modal modal--sm" onClick={e => e.stopPropagation()}>
            <h3>New Project</h3>
            <div className="modal-form">
              <label>
                <span>Project Name</span>
                <input
                  type="text"
                  value={newProjectName}
                  onChange={(e) => setNewProjectName(e.target.value)}
                  placeholder="e.g., NIFTY 50 Strategies"
                  autoFocus
                />
              </label>
              <label>
                <span>Description (optional)</span>
                <textarea
                  value={newProjectDescription}
                  onChange={(e) => setNewProjectDescription(e.target.value)}
                  placeholder="Brief description of this project..."
                  rows={3}
                />
              </label>
            </div>
            <div className="modal-actions">
              <button className="btn btn--secondary" onClick={() => setShowNewProjectModal(false)}>Cancel</button>
              <button className="btn btn--primary" onClick={handleCreateProject} disabled={creatingProject || !newProjectName.trim()}>
                {creatingProject ? <Loader2 size={ICON_SIZE} className="spinner" /> : 'Create Project'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Move Conversation Modal */}
      {showMoveDialog && moveConversationId && (
        <div className="modal-overlay" onClick={() => setShowMoveDialog(false)}>
          <div className="modal modal--sm" onClick={e => e.stopPropagation()}>
            <h3>Move Conversation</h3>
            <div className="modal-form">
              <label>
                <span>Select Project</span>
                <select
                  value={''}
                  onChange={(e) => handleMoveConversation(moveConversationId, e.target.value || null)}
                >
                  <option value="">Unassigned</option>
                  {projects.map(p => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              </label>
            </div>
            <div className="modal-actions">
              <button className="btn btn--secondary" onClick={() => setShowMoveDialog(false)}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}