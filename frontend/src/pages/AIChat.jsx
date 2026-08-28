import { useState, useRef, useEffect } from "react";

const API_BASE = "http://localhost:8000";

function AIChat() {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content:
        "Hi! I'm your AI Quant Assistant. Describe the trading strategy you'd like to build, and I'll structure it for you.",
    },
  ]);

  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showHow, setShowHow] = useState(false);
  const [attachment, setAttachment] = useState(null);

  const bottomRef = useRef(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({
      behavior: "smooth",
    });
  }, [messages, loading]);


  // =========================
  // SEND MESSAGE
  // =========================

  async function sendMessage() {
    if (!input.trim() || loading) return;

    const userMsg = {
      role: "user",
      content: input,
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          conversation_id: conversationId,
          content: userMsg.content,
        }),
      });

      if (!res.ok) {
        throw new Error("Backend request failed");
      }

      const data = await res.json();

      setConversationId(data.conversation_id);

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.reply,
        },
      ]);
    } catch (error) {
      console.error(error);

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            "Error reaching the backend. Please make sure the backend server is running.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }


  // =========================
  // FILE UPLOAD
  // =========================

  function handleFileChange(event) {
    const file = event.target.files[0];

    if (!file) return;

    const allowedTypes = [
      "application/pdf",
      "image/png",
      "image/jpeg",
      "image/jpg",
      "image/webp",
    ];

    if (!allowedTypes.includes(file.type)) {
      alert("Please upload a PDF or image file.");
      return;
    }

    setAttachment(file);
  }


  function removeAttachment() {
    setAttachment(null);

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }


  // =========================
  // FORMAT AI RESPONSE
  // =========================

  function renderMessage(content) {
    const parts = content.split(/(```(?:python)?[\s\S]*?```)/gi);

    return parts.map((part, index) => {
      if (part.startsWith("```")) {
        const code = part
          .replace(/^```python\s*/i, "")
          .replace(/^```\s*/i, "")
          .replace(/```\s*$/i, "");

        return (
          <pre className="ai-code-block" key={index}>
            <code>{code}</code>
          </pre>
        );
      }

      return (
        <div className="ai-text-block" key={index}>
          {part}
        </div>
      );
    });
  }


  return (
    <div className="ai-chat-page">

      {/* ================= HEADER ================= */}

      <div className="ai-chat-header">

        <h2>AI QUANT ASSISTANT</h2>

        <button
          className="how-button"
          onClick={() => setShowHow((prev) => !prev)}
        >
          How?
        </button>

        {showHow && (
          <div className="how-popup">

            <div className="how-popup-title">
              How it works
            </div>

            <div className="how-popup-step">
              <span>1</span>
              Describe your strategy
            </div>

            <div className="how-popup-step">
              <span>2</span>
              AI structures the logic
            </div>

            <div className="how-popup-step">
              <span>3</span>
              Get strategy code
            </div>

          </div>
        )}

      </div>


      {/* ================= CHAT ================= */}

      <div className="chat-messages">

        {messages.map((message, index) => (

          <div
            key={index}
            className={`chat-message ${message.role}`}
          >

            <div className="message-name">
              {message.role === "assistant"
                ? "✦ AI Quant"
                : "You"}
            </div>

            <div className="message-text">
              {message.role === "assistant"
                ? renderMessage(message.content)
                : message.content}
            </div>

          </div>

        ))}


        {loading && (

          <div className="chat-message assistant">

            <div className="message-name">
              ✦ AI Quant
            </div>

            <div className="message-text thinking">
              Thinking...
            </div>

          </div>

        )}

        <div ref={bottomRef} />

      </div>


      {/* ================= ATTACHMENT ================= */}

      {attachment && (

        <div className="attachment-preview">

          <span>
            {attachment.type === "application/pdf"
              ? "📄"
              : "🖼️"}
          </span>

          <span className="attachment-name">
            {attachment.name}
          </span>

          <button
            className="remove-attachment"
            onClick={removeAttachment}
          >
            ×
          </button>

        </div>

      )}


      {/* ================= INPUT ================= */}

      <div className="chat-input-area">

        <button
          className="attachment-button"
          onClick={() => fileInputRef.current?.click()}
          title="Attach image or PDF"
        >
          +
        </button>

        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,image/png,image/jpeg,image/jpg,image/webp"
          onChange={handleFileChange}
          hidden
        />

        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              sendMessage();
            }
          }}
          placeholder="Describe your trading strategy..."
          disabled={loading}
        />

        <button
          className="send-button"
          onClick={sendMessage}
          disabled={loading || !input.trim()}
          title="Send"
        >
          ↑
        </button>

      </div>

    </div>
  );
}

export default AIChat;