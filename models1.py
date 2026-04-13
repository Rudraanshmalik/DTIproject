from django.db import models

class Student(models.Model):
    name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=120, default="password123") 
    roll_number = models.CharField(max_length=50, unique=True)
    enrollment_number = models.CharField(max_length=50, unique=True)
    class_name = models.CharField(max_length=50, default="Not Assigned") 
    section = models.CharField(max_length=50, default="A")
    photo = models.ImageField(upload_to='student_photos/', blank=True, null=True)
    
    # This is the correct field for storing the path to the dataset folder.
    # The old 'embedding_path' has been removed.
    dataset_path = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.name} ({self.enrollment_number})"

