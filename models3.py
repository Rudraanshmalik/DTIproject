from django.db import models

class Developer(models.Model):
    """
    Represents the developer/administrator of the system.
    """
    name = models.CharField(max_length=120)
    email = models.CharField(max_length=120, unique=True)
    # NOTE: In a production environment, you should always store hashed passwords.
    # For this project, we are storing plain text for simplicity.
    password = models.CharField(max_length=120)


    def __str__(self):
        return self.name
    
