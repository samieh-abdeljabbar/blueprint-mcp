use serde::{Deserialize, Serialize};

pub struct User {
    pub id: u64,
    pub name: String,
    pub email: String,
}

pub enum UserRole {
    Admin,
    Member,
    Guest,
}

pub trait Repository {
    fn find_by_id(&self, id: u64) -> Option<User>;
    fn save(&self, user: &User) -> Result<(), String>;
}

pub struct InMemoryRepo {
    users: Vec<User>,
}

impl Repository for InMemoryRepo {
    fn find_by_id(&self, id: u64) -> Option<User> {
        None
    }
    fn save(&self, user: &User) -> Result<(), String> {
        Ok(())
    }
}
