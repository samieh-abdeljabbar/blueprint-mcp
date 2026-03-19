package main

import (
	"fmt"
	"github.com/gin-gonic/gin"
)

func main() {
	r := gin.Default()
	r.GET("/api/users", getUsers)
	r.POST("/api/users", createUser)
	r.Run(":8080")
}
