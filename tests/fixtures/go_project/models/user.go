package models

type User struct {
	ID    int64  `json:"id"`
	Name  string `json:"name"`
	Email string `json:"email"`
}

type UserRepository interface {
	FindByID(id int64) (*User, error)
	Save(user *User) error
}

type InMemoryUserRepo struct {
	users []User
}

func (r *InMemoryUserRepo) FindByID(id int64) (*User, error) {
	return nil, nil
}

func (r *InMemoryUserRepo) Save(user *User) error {
	return nil
}

func NewInMemoryRepo() *InMemoryUserRepo {
	return &InMemoryUserRepo{}
}
