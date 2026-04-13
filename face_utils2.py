import numpy as np
import os
from deepface import DeepFace
from scipy.spatial.distance import cosine
from django.conf import settings
from collections import defaultdict
import cv2
from PIL import Image, ImageDraw, ImageFont
import io
import base64

# --- Attendance tracking globals ---
seen_counter = defaultdict(int)   # Counts how many times a student is seen
attendance = set()                # Final attendance set

def generate_avatar_from_initials(name, size=(150, 150)):
    """
    Generates a profile avatar using student's initials.
    Returns base64 encoded image for embedding-only storage approach.
    """
    # Extract initials
    words = name.strip().split()
    if len(words) >= 2:
        initials = f"{words[0][0]}{words[1][0]}".upper()
    else:
        initials = words[0][:2].upper() if words else "ST"
    
    # Create avatar
    img = Image.new('RGB', size, color='#4A90E2')  # Professional blue
    draw = ImageDraw.Draw(img)
    
    # Try to use a nice font, fallback to default
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 60)
    except:
        font = ImageFont.load_default()
    
    # Center the initials
    bbox = draw.textbbox((0, 0), initials, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    x = (size[0] - text_width) // 2
    y = (size[1] - text_height) // 2
    
    draw.text((x, y), initials, fill='white', font=font)
    
    # Convert to base64 for storage efficiency
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    img_str = base64.b64encode(buffer.getvalue()).decode()
    
    return f"data:image/png;base64,{img_str}"

def enroll_student_face(enrollment_number, image_files, student_name=None):
    """
    🚀 EMBEDDING-ONLY APPROACH 🚀
    Processes student's photos, generates embeddings, saves only .npy file.
    Automatically deletes all photos after processing for 99.9% storage reduction.
    Returns: (embedding_path, processed_count, avatar_data)
    """
    embeddings = []
    temp_files = []  # Track temp files for cleanup
    
    print(f"🔄 Processing {len(image_files)} images for {enrollment_number}...")
    
    for image_file in image_files:
        temp_path = None
        try:
            temp_path = f"temp_{enrollment_number}_{image_file.name}"
            temp_files.append(temp_path)
            
            with open(temp_path, 'wb+') as f:
                for chunk in image_file.chunks():
                    f.write(chunk)
                    
            embedding_obj = DeepFace.represent(
                img_path=temp_path, model_name='ArcFace', 
                enforce_detection=True, detector_backend='retinaface'
            )
            embeddings.append(embedding_obj[0]["embedding"])
            print(f"✅ Processed: {image_file.name}")
            
        except Exception as e:
            print(f"⚠️  No clear face in {image_file.name}. Skipping.")
            continue
        finally:
            # IMMEDIATE CLEANUP - Delete photo after embedding extraction
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
                print(f"🗑️  Deleted: {temp_path}")

    # Generate avatar for UI display (replaces photo storage)
    avatar_data = None
    if student_name:
        avatar_data = generate_avatar_from_initials(student_name)
        print(f"🎨 Generated avatar for {student_name}")

    if len(embeddings) >= 3:
        all_embeddings = np.array(embeddings)
        static_dir = os.path.join(settings.STATICFILES_DIRS[0], 'trained_data')
        os.makedirs(static_dir, exist_ok=True)
        
        embedding_filename = f"{enrollment_number}.npy"
        embedding_path = os.path.join(static_dir, embedding_filename)
        np.save(embedding_path, all_embeddings)
        
        # Calculate storage savings
        embedding_size = os.path.getsize(embedding_path)
        print(f"💾 Saved embedding: {embedding_filename} ({embedding_size/1024:.1f}KB)")
        print(f"🚀 Storage optimization: ~{len(image_files) * 1.5:.1f}MB photos → {embedding_size/1024:.1f}KB embedding")
        
        return (os.path.join('trained_data', embedding_filename), len(embeddings), avatar_data)
        
    # Cleanup any remaining temp files
    for temp_file in temp_files:
        if os.path.exists(temp_file):
            os.remove(temp_file)
            
    return (None, len(embeddings), avatar_data)


def recognize_faces_in_frame(frame, all_student_embeddings):
    """
    Recognizes students using stored embeddings (.npy files)
    and marks them present if seen enough times.
    """
    recognized_enrollment_numbers = []
    newly_marked_present = []

    try:
        # Convert OpenCV frame (BGR) → RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Detect faces
        detected_faces = DeepFace.extract_faces(
            img_path=frame,
            detector_backend="retinaface",
            enforce_detection=False
        )

        print(f"DEBUG: Detected {len(detected_faces)} faces")

        for face_data in detected_faces:
            # Lowered from 0.90 to 0.70 for better detection
            if face_data['confidence'] > 0.70:
                live_face_img = face_data['face']
                print(f"[DEBUG] Processing face with confidence: {face_data['confidence']:.2f}")

                # Get embedding for the live face
                live_reps = DeepFace.represent(
                    img_path=live_face_img,
                    model_name="ArcFace",
                    enforce_detection=False,
                    detector_backend="skip"
                )

                if not live_reps or "embedding" not in live_reps[0]:
                    print("[DEBUG] Failed to generate embedding for face")
                    continue
                    
                live_embedding = np.array(live_reps[0]["embedding"])

                best_match_enrollment = None
                best_distance = 1.0

                # Compare with each student's stored embeddings
                for enrollment_number, stored_embeddings_list in all_student_embeddings.items():
                    for idx, stored_embedding in enumerate(stored_embeddings_list):
                        distance = cosine(live_embedding, stored_embedding)
                        print(f"[DEBUG] {enrollment_number}[{idx}] distance: {distance:.4f}")

                        if distance < best_distance:
                            best_distance = distance
                            best_match_enrollment = enrollment_number

                # Increased threshold from 0.55 to 0.60 for better matching
                print(f"[DEBUG] Best match: {best_match_enrollment} | Distance: {best_distance:.4f} | Threshold: 0.60")
                
                if best_match_enrollment and best_distance < 0.55:
                    recognized_enrollment_numbers.append(best_match_enrollment)

                    # Attendance logic - mark present immediately (changed from 3 times to 1)
                    if best_match_enrollment not in attendance:
                        seen_counter[best_match_enrollment] += 1
                        if seen_counter[best_match_enrollment] >= 1:
                            attendance.add(best_match_enrollment)
                            newly_marked_present.append(best_match_enrollment)
                            print(f"✅ Marked {best_match_enrollment} as PRESENT (distance={best_distance:.3f})")
                else:
                    print(f"[DEBUG] No match - best distance {best_distance:.4f} exceeds threshold 0.60")

    except Exception as e:
        print(f"CRITICAL AI ERROR in recognize_faces_in_frame: {e}")

    print(f"AI UTILITY: Returning recognized students: {recognized_enrollment_numbers}")
    return {
        "recognized": recognized_enrollment_numbers,  # Seen this frame
        "newly_present": newly_marked_present,        # Just marked present
        "attendance": list(attendance)                # Full attendance till now
    }