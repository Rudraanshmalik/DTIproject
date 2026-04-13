from django.db import models
from student.models import Student
from teacher.models import Teacher
from django.utils import timezone

class AttendanceSession(models.Model):
    """ Represents a single attendance-taking event for a specific class. """
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE)
    class_name = models.CharField(max_length=100)
    section = models.CharField(max_length=50)
    session_date = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Attendance for {self.class_name} - {self.section} on {self.session_date}"

class AttendanceRecord(models.Model):
    """ Stores the attendance status for a single student in a session. """
    session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE, related_name='records')
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=[('Present', 'Present'), ('Absent', 'Absent')], default='Absent')

    def __str__(self):
        return f"{self.student.name} - {self.status}"

