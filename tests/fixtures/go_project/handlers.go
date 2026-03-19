package main

import "github.com/gin-gonic/gin"

func getUsers(c *gin.Context) {
	c.JSON(200, []string{})
}

func createUser(c *gin.Context) {
	c.JSON(201, gin.H{"status": "created"})
}
