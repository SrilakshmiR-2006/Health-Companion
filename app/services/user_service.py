"""User service: get and create users."""
import secrets
import string

from app.models.user import User


def get_user_by_id(session, user_id):
    """Return the User with the given id, or None if not found."""
    return session.query(User).filter(User.id == user_id).first()


def get_user_by_profile_code(session, profile_code):
    """Return the User with the given profile_code, or None if not found."""
    if not profile_code or not str(profile_code).strip():
        return None
    return session.query(User).filter(User.profile_code == str(profile_code).strip().upper()).first()


def get_user_by_email(session, email):
    """Return the User with the given email, or None if not found. Case-insensitive."""
    if not email or not str(email).strip():
        return None
    return session.query(User).filter(User.email.ilike(str(email).strip())).first()


def _generate_profile_code(session, length=8):
    """Return a unique uppercase alphanumeric code."""
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(50):
        code = "".join(secrets.choice(alphabet) for _ in range(length))
        if session.query(User).filter(User.profile_code == code).first() is None:
            return code
    raise RuntimeError("Could not generate unique profile_code")


def create_user(
    session,
    name,
    age,
    gender,
    height_cm,
    weight_kg,
    goal,
    dietary_preference,
    budget,
    equipment,
    workout_minutes_per_day,
    email=None,
    cuisine=None,
):
    """Create a new user with a unique profile_code, save to DB, and return it."""
    user = User(
        profile_code=_generate_profile_code(session),
        name=name,
        age=age,
        gender=gender,
        height_cm=height_cm,
        weight_kg=weight_kg,
        goal=goal,
        dietary_preference=dietary_preference,
        cuisine=(cuisine.strip() if cuisine and str(cuisine).strip() else None) or None,
        budget=float(budget),
        equipment=equipment,
        workout_minutes_per_day=int(workout_minutes_per_day),
        email=email.strip() if email and str(email).strip() else None,
    )
    session.add(user)
    session.commit()
    session.refresh(user)  # so user.id is set
    return user


def update_user_preferences(
    session,
    user_id,
    name,
    age,
    gender,
    height_cm,
    weight_kg,
    goal,
    dietary_preference,
    budget,
    equipment,
    workout_minutes_per_day,
    email=None,
    cuisine=None,
):
    """
    Update an existing user's core preferences (name, goal, body metrics, budget, equipment, email, cuisine).
    Returns the updated User or None if not found.
    """
    user = get_user_by_id(session, user_id)
    if not user:
        return None

    user.name = name
    user.age = int(age)
    user.gender = gender
    user.height_cm = float(height_cm)
    user.weight_kg = float(weight_kg)
    user.goal = goal
    user.dietary_preference = dietary_preference
    user.cuisine = (cuisine.strip() if cuisine and str(cuisine).strip() else None) or None
    user.budget = float(budget)
    user.equipment = equipment
    user.workout_minutes_per_day = int(workout_minutes_per_day)
    user.email = email.strip() if email and str(email).strip() else None

    session.commit()
    session.refresh(user)
    return user