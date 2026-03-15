import os
import shutil
from django.conf import settings
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.db.models import Count, Q
from datetime import datetime, timedelta
from django.utils import timezone
from django.contrib.sessions.models import Session

from .models import Student
from attendance.models import AttendanceRecord, AttendanceSession
from core.face_utils import enroll_student_face

# Store active session keys for each user
ACTIVE_SESSIONS = {}

def public_student_register(request):
    """
    DISABLED FOR SECURITY: Student self-registration is restricted.
    Students must be registered by developers or teachers only.
    """
    messages.error(request, 
        '🚫 Student self-registration is disabled for security reasons. '
        'Please contact your teacher or administrator to register your account.'
    )
    return redirect('home_page')
    
    # Original registration code disabled below:
    if False and request.method == 'POST':
        enrollment_number = request.POST.get('enrollment_number')
        images = request.FILES.getlist('images')

        if len(images) < 3:
            messages.error(request, 'Please upload at least 3 clear photos for the face dataset.')
            return render(request, 'student_form.html', {'form_data': request.POST})

        if Student.objects.filter(enrollment_number=enrollment_number).exists():
            messages.error(request, f"A student with enrollment number '{enrollment_number}' already exists.")
            return render(request, 'student_form.html', {'form_data': request.POST})

        # 🚀 EMBEDDING-ONLY APPROACH: Process images and generate avatar
        student_name = request.POST.get('name')
        dataset_path, success_count, avatar_data = enroll_student_face(
            enrollment_number, images, student_name
        )
        
        if dataset_path:
            # Create student with embedding-only storage (no photo field)
            student = Student.objects.create(
                name=student_name,
                email=request.POST.get('email'),
                roll_number=request.POST.get('roll_number'),
                enrollment_number=enrollment_number,
                class_name=request.POST.get('class_name'),
                section=request.POST.get('section'),
                dataset_path=dataset_path
                # NOTE: No photo field - using avatar_data for UI display
            )
            
            # Store avatar data in session for immediate display
            if avatar_data:
                request.session[f'avatar_{enrollment_number}'] = avatar_data
            
            embedding_size = 12  # Approximate KB per student
            total_images = len(images)
            saved_mb = total_images * 1.5  # Approximate MB saved
            
            messages.success(
                request, 
                f'✅ You have been registered successfully! '
                f'Storage optimized: {saved_mb:.1f}MB photos → {embedding_size}KB embedding '
                f'(99.2% reduction). A developer will review your profile.'
            )
            return redirect('home_page') # Redirect to the main home page
        else:
            messages.error(
                request, 
                f'⚠️  AI could only process {success_count} of {len(images)} uploaded images. '
                f'Please try again with clearer, well-lit photos showing the face clearly.'
            )
    
    return render(request, 'student_form.html')


def student_login(request):
    """
    Handles student login functionality.
    Automatically logs out any existing sessions for the same student.
    """
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        try:
            student = Student.objects.get(email=email, password=password)
            
            # Check if this student has an active session elsewhere
            student_key = f'student_{student.id}'
            if student_key in ACTIVE_SESSIONS:
                old_session_key = ACTIVE_SESSIONS[student_key]
                try:
                    # Delete the old session
                    Session.objects.filter(session_key=old_session_key).delete()
                except:
                    pass
            
            # Create new session
            request.session['student_id'] = student.id
            request.session['student_name'] = student.name
            request.session.save()
            
            # Store new session key
            ACTIVE_SESSIONS[student_key] = request.session.session_key
            
            return redirect('student_dashboard')
        except Student.DoesNotExist:
            messages.error(request, 'Invalid email or password.')
            return redirect('student_login')
    return render(request, 'student_login.html')


def student_dashboard(request):
    """
    Displays the student's dashboard with attendance overview.
    """
    student_id = request.session.get('student_id')
    if not student_id:
        messages.warning(request, 'Your session has expired or you logged in from another device. Please log in again.')
        return redirect('student_login')
    
    try:
        student = Student.objects.get(id=student_id)
        
        # Get attendance statistics
        total_sessions = AttendanceSession.objects.filter(
            class_name=student.class_name,
            section=student.section
        ).count()
        
        present_count = AttendanceRecord.objects.filter(
            student=student,
            status='present'
        ).count()
        
        absent_count = AttendanceRecord.objects.filter(
            student=student,
            status='absent'
        ).count()
        
        # Calculate attendance percentage
        total_records = present_count + absent_count
        attendance_percentage = round((present_count / total_records * 100), 2) if total_records > 0 else 0
        
        # Get recent attendance records
        recent_attendance = AttendanceRecord.objects.filter(
            student=student
        ).select_related('session', 'session__teacher').order_by('-session__session_date', '-session__created_at')[:10]
        
        context = {
            'student': student,
            'total_sessions': total_sessions,
            'present_count': present_count,
            'absent_count': absent_count,
            'total_records': total_records,
            'attendance_percentage': attendance_percentage,
            'recent_attendance': recent_attendance,
        }
        return render(request, 'student_dashboard.html', context)
    except Student.DoesNotExist:
        messages.error(request, 'Student profile not found.')
        return redirect('student_login')


def student_attendance_history(request):
    """
    Shows complete attendance history for the student.
    """
    student_id = request.session.get('student_id')
    if not student_id:
        messages.error(request, 'You must be logged in to view attendance history.')
        return redirect('student_login')
    
    try:
        student = Student.objects.get(id=student_id)
        
        # Get all attendance records
        attendance_records = AttendanceRecord.objects.filter(
            student=student
        ).select_related('session', 'session__teacher').order_by('-session__session_date', '-session__created_at')
        
        # Filter by date range if provided
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        if start_date:
            attendance_records = attendance_records.filter(session__session_date__gte=start_date)
        if end_date:
            attendance_records = attendance_records.filter(session__session_date__lte=end_date)
        
        # Monthly statistics
        today = timezone.now().date()
        this_month_start = today.replace(day=1)
        
        monthly_present = AttendanceRecord.objects.filter(
            student=student,
            session__session_date__gte=this_month_start,
            status='present'
        ).count()
        
        monthly_absent = AttendanceRecord.objects.filter(
            student=student,
            session__session_date__gte=this_month_start,
            status='absent'
        ).count()
        
        context = {
            'student': student,
            'attendance_records': attendance_records,
            'monthly_present': monthly_present,
            'monthly_absent': monthly_absent,
            'start_date': start_date,
            'end_date': end_date,
        }
        return render(request, 'student_attendance_history.html', context)
    except Student.DoesNotExist:
        messages.error(request, 'Student profile not found.')
        return redirect('student_login')


def student_profile(request):
    """
    Shows and allows editing of student profile.
    """
    student_id = request.session.get('student_id')
    if not student_id:
        messages.error(request, 'You must be logged in to view your profile.')
        return redirect('student_login')
    
    try:
        student = Student.objects.get(id=student_id)
        
        if request.method == 'POST':
            # Update allowed fields only
            student.email = request.POST.get('email', student.email)
            if request.POST.get('password'):
                student.password = request.POST.get('password')
            
            if request.FILES.get('photo'):
                student.photo = request.FILES.get('photo')
            
            student.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('student_profile')
        
        context = {'student': student}
        return render(request, 'student_profile.html', context)
    except Student.DoesNotExist:
        messages.error(request, 'Student profile not found.')
        return redirect('student_login')


def student_logout(request):
    """
    Logs out the student.
    """
    request.session.flush()
    messages.success(request, 'You have been logged out successfully.')
    return redirect('student_login')
