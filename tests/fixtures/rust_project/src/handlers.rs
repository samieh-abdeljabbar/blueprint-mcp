use crate::models;
use actix_web::{web, HttpResponse};

#[get("/api/users")]
pub async fn get_users() -> HttpResponse {
    HttpResponse::Ok().json(Vec::<String>::new())
}

#[post("/api/users")]
pub async fn create_user() -> HttpResponse {
    HttpResponse::Created().finish()
}
