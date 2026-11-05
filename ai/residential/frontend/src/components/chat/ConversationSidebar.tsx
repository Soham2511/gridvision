import React, { useState, useMemo } from 'react';
import {
  Plus,
  MessageSquare,
  Edit2,
  Trash2,
  Archive,
  Check,
  X,
  ChevronLeft,
  ChevronRight,
  Clock,
} from 'lucide-react';

export interface ConversationItem {
  id: string;
  conversation_id?: string;
  title: string;
  updated_at?: string | null;
  created_at?: string | null;
  active_workflow?: string | null;
  is_archived?: boolean;
  is_title_custom?: boolean;
  message_count?: number;
}

interface ConversationSidebarProps {
  conversations: ConversationItem[];
  activeConversationId: string | null;
  onSelectConversation: (id: string) => void;
  onNewChat: () => void;
  onRenameConversation: (id: string, newTitle: string) => Promise<void>;
  onDeleteConversation: (id: string) => Promise<void>;
  onArchiveConversation?: (id: string, isArchived: boolean) => Promise<void>;
  isLoading?: boolean;
}

export const ConversationSidebar: React.FC<ConversationSidebarProps> = ({
  conversations,
  activeConversationId,
  onSelectConversation,
  onNewChat,
  onRenameConversation,
  onDeleteConversation,
  onArchiveConversation,
  isLoading = false,
}) => {
  const [isCollapsed, setIsCollapsed] = useState<boolean>(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState<string>('');
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState<boolean>(false);

  // Group conversations by relative time: Today, Yesterday, Previous 7 Days, Older
  const groupedConversations = useMemo(() => {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const oneDayMs = 24 * 60 * 60 * 1000;

    const groups: {
      today: ConversationItem[];
      yesterday: ConversationItem[];
      last7Days: ConversationItem[];
      older: ConversationItem[];
    } = {
      today: [],
      yesterday: [],
      last7Days: [],
      older: [],
    };

    const filtered = conversations.filter((c) => (showArchived ? c.is_archived : !c.is_archived));

    filtered.forEach((conv) => {
      const dateStr = conv.updated_at || conv.created_at;
      if (!dateStr) {
        groups.today.push(conv);
        return;
      }

      const itemDate = new Date(dateStr);
      const itemDay = new Date(itemDate.getFullYear(), itemDate.getMonth(), itemDate.getDate()).getTime();
      const diffDays = Math.floor((today - itemDay) / oneDayMs);

      if (diffDays <= 0) {
        groups.today.push(conv);
      } else if (diffDays === 1) {
        groups.yesterday.push(conv);
      } else if (diffDays <= 7) {
        groups.last7Days.push(conv);
      } else {
        groups.older.push(conv);
      }
    });

    return groups;
  }, [conversations, showArchived]);

  const handleStartRename = (conv: ConversationItem, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(conv.id);
    setEditingTitle(conv.title || 'New Chat');
  };

  const handleSaveRename = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const trimmed = editingTitle.trim();
    if (trimmed && trimmed.length <= 100) {
      await onRenameConversation(id, trimmed);
    }
    setEditingId(null);
  };

  const handleCancelRename = (e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(null);
  };

  const handleConfirmDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    await onDeleteConversation(id);
    setDeletingId(null);
  };

  if (isCollapsed) {
    return (
      <div
        style={{
          width: '48px',
          backgroundColor: '#FFFFFF',
          border: '1px solid #E2E8F0',
          borderRadius: '12px',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          padding: '1rem 0.5rem',
          gap: '1rem',
          height: 'fit-content',
          boxShadow: '0 1px 3px rgba(11, 31, 51, 0.04)',
        }}
      >
        <button
          type="button"
          title="Expand sidebar"
          onClick={() => setIsCollapsed(false)}
          style={{
            background: 'transparent',
            border: 'none',
            color: '#64748B',
            cursor: 'pointer',
            padding: '0.4rem',
            borderRadius: '6px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <ChevronRight size={18} />
        </button>

        <button
          type="button"
          title="New Chat"
          onClick={onNewChat}
          style={{
            background: 'linear-gradient(135deg, #00B8A9, #087EBD)',
            border: 'none',
            color: '#FFFFFF',
            cursor: 'pointer',
            padding: '0.5rem',
            borderRadius: '8px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 2px 4px rgba(0, 184, 169, 0.2)',
          }}
        >
          <Plus size={18} />
        </button>
      </div>
    );
  }

  const renderConversationGroup = (title: string, items: ConversationItem[]) => {
    if (items.length === 0) return null;

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', marginBottom: '1rem' }}>
        <div
          style={{
            fontSize: '0.68rem',
            fontWeight: 700,
            color: '#94A3B8',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            padding: '0 0.5rem 0.25rem 0.5rem',
          }}
        >
          {title}
        </div>
        {items.map((conv) => {
          const isActive = conv.id === activeConversationId;
          const isEditing = conv.id === editingId;
          const isDeleting = conv.id === deletingId;

          return (
            <div
              key={conv.id}
              onClick={() => onSelectConversation(conv.id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '0.55rem 0.65rem',
                borderRadius: '8px',
                cursor: 'pointer',
                backgroundColor: isActive ? '#E0F7F5' : 'transparent',
                border: isActive ? '1px solid #00B8A9' : '1px solid transparent',
                transition: 'all 0.15s ease',
                position: 'relative',
              }}
              onMouseEnter={(e) => {
                if (!isActive) {
                  e.currentTarget.style.backgroundColor = '#F8FAFC';
                }
              }}
              onMouseLeave={(e) => {
                if (!isActive) {
                  e.currentTarget.style.backgroundColor = 'transparent';
                }
              }}
            >
              {isEditing ? (
                <div
                  style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', width: '100%' }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <input
                    type="text"
                    value={editingTitle}
                    onChange={(e) => setEditingTitle(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleSaveRename(conv.id, e as any);
                      if (e.key === 'Escape') handleCancelRename(e as any);
                    }}
                    autoFocus
                    maxLength={100}
                    style={{
                      flex: 1,
                      fontSize: '0.8rem',
                      padding: '0.2rem 0.4rem',
                      borderRadius: '4px',
                      border: '1px solid #00B8A9',
                      outline: 'none',
                    }}
                  />
                  <button
                    type="button"
                    onClick={(e) => handleSaveRename(conv.id, e)}
                    style={{ background: 'none', border: 'none', color: '#00B8A9', cursor: 'pointer', padding: '0.2rem' }}
                  >
                    <Check size={14} />
                  </button>
                  <button
                    type="button"
                    onClick={handleCancelRename}
                    style={{ background: 'none', border: 'none', color: '#64748B', cursor: 'pointer', padding: '0.2rem' }}
                  >
                    <X size={14} />
                  </button>
                </div>
              ) : isDeleting ? (
                <div
                  style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', gap: '0.5rem' }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <span style={{ fontSize: '0.75rem', color: '#B91C1C', fontWeight: 600 }}>Delete chat?</span>
                  <div style={{ display: 'flex', gap: '0.25rem' }}>
                    <button
                      type="button"
                      onClick={(e) => handleConfirmDelete(conv.id, e)}
                      style={{
                        backgroundColor: '#DC2626',
                        color: '#FFFFFF',
                        border: 'none',
                        borderRadius: '4px',
                        padding: '0.15rem 0.45rem',
                        fontSize: '0.7rem',
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      Yes
                    </button>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setDeletingId(null);
                      }}
                      style={{
                        backgroundColor: '#E2E8F0',
                        color: '#475569',
                        border: 'none',
                        borderRadius: '4px',
                        padding: '0.15rem 0.45rem',
                        fontSize: '0.7rem',
                        cursor: 'pointer',
                      }}
                    >
                      No
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      overflow: 'hidden',
                      flex: 1,
                    }}
                  >
                    <MessageSquare size={14} color={isActive ? '#00B8A9' : '#64748B'} style={{ flexShrink: 0 }} />
                    <span
                      title={conv.title || 'New Chat'}
                      style={{
                        fontSize: '0.8rem',
                        fontWeight: isActive ? 700 : 500,
                        color: isActive ? '#0B1F33' : '#334155',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {conv.title || 'New Chat'}
                    </span>
                  </div>

                  {/* Action buttons (Rename, Archive, Delete) */}
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.25rem',
                      opacity: isActive ? 1 : 0.7,
                      flexShrink: 0,
                    }}
                  >
                    <button
                      type="button"
                      title="Rename conversation"
                      onClick={(e) => handleStartRename(conv, e)}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: '#64748B',
                        cursor: 'pointer',
                        padding: '0.2rem',
                        borderRadius: '4px',
                      }}
                    >
                      <Edit2 size={12} />
                    </button>

                    {onArchiveConversation && (
                      <button
                        type="button"
                        title={conv.is_archived ? 'Unarchive' : 'Archive'}
                        onClick={(e) => {
                          e.stopPropagation();
                          onArchiveConversation(conv.id, !conv.is_archived);
                        }}
                        style={{
                          background: 'transparent',
                          border: 'none',
                          color: conv.is_archived ? '#00B8A9' : '#64748B',
                          cursor: 'pointer',
                          padding: '0.2rem',
                          borderRadius: '4px',
                        }}
                      >
                        <Archive size={12} />
                      </button>
                    )}

                    <button
                      type="button"
                      title="Delete conversation"
                      onClick={(e) => {
                        e.stopPropagation();
                        setDeletingId(conv.id);
                      }}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: '#94A3B8',
                        cursor: 'pointer',
                        padding: '0.2rem',
                        borderRadius: '4px',
                      }}
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </>
              )}
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <aside
      style={{
        width: '260px',
        backgroundColor: '#FFFFFF',
        border: '1px solid #E2E8F0',
        borderRadius: '12px',
        display: 'flex',
        flexDirection: 'column',
        boxShadow: '0 1px 3px rgba(11, 31, 51, 0.04)',
        height: '660px',
        flexShrink: 0,
        overflow: 'hidden',
      }}
    >
      {/* Sidebar Header */}
      <div
        style={{
          padding: '1rem',
          borderBottom: '1px solid #E2E8F0',
          display: 'flex',
          flexDirection: 'column',
          gap: '0.75rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <Clock size={16} color="#00B8A9" />
            <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#0B1F33' }}>Chat History</span>
          </div>

          <button
            type="button"
            title="Collapse sidebar"
            onClick={() => setIsCollapsed(true)}
            style={{
              background: 'transparent',
              border: 'none',
              color: '#64748B',
              cursor: 'pointer',
              padding: '0.25rem',
              borderRadius: '4px',
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <ChevronLeft size={16} />
          </button>
        </div>

        {/* New Chat Button */}
        <button
          type="button"
          onClick={onNewChat}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '0.5rem',
            width: '100%',
            padding: '0.6rem 0.75rem',
            borderRadius: '8px',
            background: 'linear-gradient(135deg, #00B8A9, #087EBD)',
            color: '#FFFFFF',
            border: 'none',
            fontSize: '0.82rem',
            fontWeight: 700,
            cursor: 'pointer',
            boxShadow: '0 2px 4px rgba(0, 184, 169, 0.15)',
            transition: 'all 0.15s ease',
          }}
        >
          <Plus size={16} />
          <span>New Chat</span>
        </button>
      </div>

      {/* Conversations List with Date Grouping */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '0.75rem 0.5rem',
        }}
      >
        {isLoading && conversations.length === 0 ? (
          <div style={{ textAlign: 'center', color: '#94A3B8', fontSize: '0.78rem', padding: '2rem 1rem' }}>
            Loading conversations...
          </div>
        ) : conversations.length === 0 ? (
          <div style={{ textAlign: 'center', color: '#94A3B8', fontSize: '0.78rem', padding: '2rem 1rem' }}>
            No conversations yet. Start a new chat!
          </div>
        ) : (
          <>
            {renderConversationGroup('Today', groupedConversations.today)}
            {renderConversationGroup('Yesterday', groupedConversations.yesterday)}
            {renderConversationGroup('Previous 7 Days', groupedConversations.last7Days)}
            {renderConversationGroup('Older', groupedConversations.older)}
          </>
        )}
      </div>

      {/* Sidebar Footer: Toggle Archive view */}
      {onArchiveConversation && (
        <div
          style={{
            padding: '0.6rem 1rem',
            borderTop: '1px solid #E2E8F0',
            backgroundColor: '#F8FAFC',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: '0.72rem',
            color: '#64748B',
          }}
        >
          <span>{showArchived ? 'Viewing Archived' : 'Active Chats'}</span>
          <button
            type="button"
            onClick={() => setShowArchived((prev) => !prev)}
            style={{
              background: 'transparent',
              border: 'none',
              color: '#087EBD',
              cursor: 'pointer',
              fontWeight: 600,
              textDecoration: 'underline',
              fontSize: '0.72rem',
            }}
          >
            {showArchived ? 'View Active' : 'View Archived'}
          </button>
        </div>
      )}
    </aside>
  );
};

