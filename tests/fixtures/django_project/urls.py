from django.urls import path
from . import views

urlpatterns = [
    path("authors/", views.author_list, name="author-list"),
    path("authors/<int:pk>/", views.author_detail, name="author-detail"),
    path("books/", views.BookListView.as_view(), name="book-list"),
]
