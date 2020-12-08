import os
import csv
import sys

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, jsonify, make_response, Response, url_for
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from datetime import date

from helpers import apology, login_required

# UPLOAD_FOLDER = '/uploads'
UPLOAD_FOLDER = '../participation/uploads'
ALLOWED_EXTENSIONS = {'txt', 'csv'}

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Configure session to use filesystem (instead of signed cookies)
# app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure upload folder
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Configure CS50 Library to use SQLite database
db = SQL(os.environ.get("DATABASE_URL"))


@app.route("/")
@login_required
def index():
    """Home Page"""
    # return apology("TODO")
    return redirect("/participation")


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_file():
    if request.method == 'POST':

        # Get Class and Time Period
        if request.form.get("class_id") == "0":
            return apology("must choose a class", 403)

        # check if the post request has the file part
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        file = request.files['file']
        # if user does not select file, browser also
        # submit an empty part without filename
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        # Open file and save students in SQL
        class_id = request.form.get("class_id")
        f = open(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        reader = csv.DictReader(f)
        fields = reader.fieldnames

        for row in reader:
            id = row["ID"]
            course = row["Course"]

            student = db.execute("SELECT * FROM students WHERE student_id = ?", id)
            if len(student) == 0:
                db.execute("INSERT INTO students (last_name, first_name, student_id) VALUES(?, ?, ?)", row["LastName"], row["FirstName"], id)

            # rows = db.execute("SELECT id FROM classes WHERE class_name = ?", request.form.get("class_name"))
            db.execute("INSERT INTO students_classes (student_id, class_id) VALUES(?, ?)", id, class_id)

        f.close()
        flash('Students uploaded')
        return redirect('/students')

    # GET request
    else:
        classes = db.execute("SELECT * FROM classes WHERE teacher_id = ?", session["user_id"])
        return render_template("upload.html", classes=classes)


@app.route("/participation")
@login_required
def participation():
    """Track Student Participation"""

    classes = db.execute("SELECT * FROM classes WHERE teacher_id = ?", session["user_id"])
    return render_template("select_class.html", classes=classes)


@app.route("/select")
@login_required
def select():
    """Select Class and Display Students for Selection"""

    selected_class = request.args.get('class')
    print("CLASS is: ", selected_class)

    # Select student for this addClass
    student_list = []
    students = db.execute("SELECT * FROM students WHERE student_id IN (SELECT student_id FROM students_classes where class_id = ?)", selected_class)
    # print(students)
    for student in students:
        # student_list.append(student['name'][:15] + '\n' + str(student['student_id']))
        student_list.append((student['first_name'], student['last_name'], student['student_id']))
    student_list.sort()
    # classes = db.execute("SELECT * FROM classes WHERE teacher_id = ?", session["user_id"])
    class_name = db.execute("SELECT class_name FROM classes WHERE id = ?", selected_class)
    return render_template("track.html", students=student_list, selected_class=selected_class, class_name=class_name[0]['class_name'])


@app.route('/save', methods=['GET', 'POST'])
@login_required
def save():
    """Save Student Participation Points"""

    # POST request
    if request.method == 'POST':
        print('Incoming..')
        selected_students = request.get_json()  # parse as JSON
        print(selected_students)

        # Check JSON
        selected_class = selected_students["selected_class"]
        print("CLASS:",selected_class)
        participation_credit = selected_students['points']
        print("PC:",participation_credit)

        for student in participation_credit:
            id = student[1]
            dt_time = date.today()
            datenow = 10000*dt_time.year + 100*dt_time.month + dt_time.day
            db.execute("""INSERT INTO participation (teacher_id, class_id, student_id, date, points)
                        VALUES (?, ?, ?, ?, ?)""", session["user_id"], selected_class, id, datenow, 1)
        return 'OK', 200

    # GET request
    else:
        message = {'greeting':'Hello from Flask!'}
        return jsonify(message)  # serialize and use JSON headers


@app.route('/download/<string:dfilename>')
def generate_large_csv(dfilename):
    def generate():
        try:
            for row in contents:
                yield ','.join(row) + '\n'
#         except NameError:
#             flash("Problem downloading, try again.")
#             return
    return Response(generate(), mimetype='text/csv')


@app.route("/report", methods=["GET", "POST"])
@login_required
def report():
    """Create Participation Report"""

    if request.method == "POST":
        # Get Class and Time Period
        if request.form.get("class_id") == "0":
            return apology("must choose a class", 403)

        if not request.form.get("start_date"):
            return apology("must choose start date", 403)

        if not request.form.get("end_date"):
            return apology("must choose end date", 403)

        date = request.form.get("start_date")
        start_date = int(date[:4] + date[5:7] + date[8:])
        date = request.form.get("end_date")
        end_date = int(date[:4] + date[5:7] + date[8:])

        print(request.form.get("class_id"))

        participation = db.execute("""SELECT student_id, SUM(points) AS points FROM participation
                                    WHERE teacher_id = ? AND class_id = ? AND date >= ? and date <= ?
                                    GROUP BY student_id""", session["user_id"], request.form.get("class_id"), start_date, end_date)
        classes = db.execute("SELECT * FROM classes WHERE id = ? AND teacher_id = ?", request.form.get("class_id"), session["user_id"])
        print(classes)

        course_code = classes[0]['class_code']
        section = classes[0]['section']

        # Create file to upload to skedula
        global dfilename
        dfilename = classes[0]['class_name'] + '-' + str(start_date)  + '-' +  str(end_date) + ".csv"
        # file = open(skedula_file, "w")
        # writer = csv.writer(file)
        # writer.writerow((["LastName","FirstName","ID","Course","Section","Grade"]))

        global contents
        contents = [["LastName","FirstName","ID","Course","Section","Grade"]]

        # Write row for each student
        for row in participation:
            # print(row)
            student = db.execute("SELECT * FROM students WHERE student_id = ?", row['student_id'])
            # print(student[0]['last_name'])
            contents.append([student[0]['last_name'], student[0]['first_name'], str(student[0]['student_id']), course_code, str(section), str(row['points'])])
            # writer.writerow(([student[0]['last_name'], student[0]['first_name'], student[0]['student_id'], course_code, section, row['points']]))
        # file.close()
        # print(contents)

        # return redirect('/<filename>')
        return redirect(url_for('generate_large_csv', dfilename=dfilename))
        return redirect("/report")

    # GET Request
    else:
        classes = db.execute("SELECT * FROM classes WHERE teacher_id = ?", session["user_id"])
        return render_template("report.html", classes=classes)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/classes", methods=["GET", "POST"])
@login_required
def classes():
    """Add classes"""

    if request.method == "POST":

        # Ensure class info input
        if not request.form.get("class_name"):
            return apology("must provide class name", 403)

        if '/' in request.form.get("class_name"):
            flash("Invalid class name! Cannot use '/' in class name")
            return redirect('classes')

        if not request.form.get("period"):
            return apology("must provide class period", 403)

        if not request.form.get("code"):
            return apology("must provide class code", 403)
        
        if not request.form.get("class_section"):
            return apology("must provide class section", 403)

        # Add class to database
        try:
            class_id = db.execute("INSERT INTO classes (teacher_id, class_name, class_period, class_code, section) VALUES(?, ?, ?, ?, ?)",
                            session["user_id"],
                            request.form.get("class_name"),
                            request.form.get("period"),
                            request.form.get("code"),
                            request.form.get("class_section"))
        except RuntimeError:
            return apology("class already exists")

        # flash("Registered!")
        return redirect("/classes")

    # GET
    else:
        classes = db.execute("SELECT * FROM classes WHERE teacher_id = ?", session["user_id"])
        return render_template("add_classes.html", classes=classes)


@app.route("/students", methods=["GET", "POST"])
@login_required
def students():
    """Add students"""

    # POST
    if request.method == "POST":
        # Ensure class info input
        if not request.form.get("class_id"):
            return apology("must choose a class", 403)

        if not request.form.get("first_name") or not request.form.get("last_name"):
            return apology("must provide student name", 403)

        if not request.form.get("student_id"):
            return apology("must provide student_id", 403)

        student = db.execute("SELECT * FROM students WHERE student_id = ?", request.form.get("student_id"))

        if len(student) == 0:
            db.execute("INSERT INTO students (first_name, last_name, student_id) VALUES(?, ?, ?)",
                                request.form.get("first_name"),
                                request.form.get("last_name"),
                                request.form.get("student_id"))

        # rows = db.execute("SELECT id FROM classes WHERE class_name = ?", request.form.get("class_name"))
        db.execute("INSERT INTO students_classes (student_id, class_id) VALUES(?, ?)", request.form.get("student_id"), request.form.get("class_id"))
        return redirect("/students")
    else:
        classes = db.execute("SELECT * FROM classes WHERE teacher_id = ?", session["user_id"])
        return render_template("students.html", classes=classes)


# @app.route('/test')
# def test_page():
#     # look inside `templates` and serve `index.html`
#     return render_template('index.html')

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user for an account."""

    # POST
    if request.method == "POST":

        # Validate form submission
        if not request.form.get("username"):
            return apology("missing username")
        elif not request.form.get("password"):
            return apology("missing password")
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords don't match")

        # Add user to database
        try:
            id = db.execute("INSERT INTO users (username, hash) VALUES(?, ?)",
                            request.form.get("username"),
                            generate_password_hash(request.form.get("password")))
        except RuntimeError:
            return apology("username taken")

        # Log user in
        session["user_id"] = id

        # Let user know they're registered
        flash("Registered!")
        return redirect("/")

    # GET
    else:
        return render_template("register.html")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
