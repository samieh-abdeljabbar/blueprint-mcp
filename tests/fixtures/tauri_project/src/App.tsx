import { invoke } from "@tauri-apps/api/core";
import { useState, useEffect } from "react";

export default function App() {
    const [notes, setNotes] = useState([]);

    useEffect(() => {
        invoke("get_notes").then(setNotes);
    }, []);

    async function handleSave(title, content) {
        await invoke("save_note", { title, content });
        const updated = await invoke("get_notes");
        setNotes(updated);
    }

    async function handleDelete(id) {
        await invoke("delete_note", { id });
    }

    return (
        <div>
            <h1>Notes</h1>
            {notes.map(n => <div key={n.id}>{n.title}</div>)}
        </div>
    );
}
