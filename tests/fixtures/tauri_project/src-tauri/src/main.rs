use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize)]
struct Note {
    id: u64,
    title: String,
    content: String,
}

#[tauri::command]
async fn get_notes() -> Vec<Note> {
    vec![]
}

#[tauri::command]
fn save_note(title: String, content: String) -> bool {
    true
}

#[tauri::command]
fn delete_note(id: u64) -> bool {
    true
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![get_notes, save_note, delete_note])
        .run(tauri::generate_context!())
        .expect("error running tauri application");
}
