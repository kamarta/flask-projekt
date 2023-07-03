import os
from flask import Flask, render_template, redirect, request, url_for, flash, send_from_directory, abort, send_file, make_response #send_file teraz nie potrzebne
from werkzeug.utils import secure_filename
from werkzeug.urls import url_parse
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, current_user, login_user, login_required, logout_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, FileField, MultipleFileField, validators
from flask_wtf.file import FileAllowed, FileRequired
from wtforms.validators import DataRequired, ValidationError, Email, EqualTo
import io
import fitz 
from PIL import Image, ImageDraw, ImageFont
import csv
from flask_mail import Mail, Message
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from io import BytesIO
import zipfile

os.environ['FLASK_APP'] = 'app.py'

class Config(object):
    SECRET_KEY = os.environ.get('SECRET_KEY') or '7553367355c48d178a9c6ce1563c7e866392c7d67b9651488519023018e26b09'
    basedir = os.path.abspath(os.path.dirname(__file__))

    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False



app = Flask(__name__)
app.config.from_object(Config)


db = SQLAlchemy(app)
migrate = Migrate(app, db)
login = LoginManager(app)

login.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(128))

    def __repr__(self):
        return '<User {}>'.format(self.username)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

@login.user_loader
def load_user(id):
    return User.query.get(int(id))


class Upload(db.Model):

    __tablename__ = 'uploads'

    id = db.Column(db.Integer, primary_key = True)
    filename = db.Column(db.String)
    data = db.Column(db.LargeBinary)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))


    def __repr__(self):
        return '<Upload {}>'.format(self.filename)
    
    user = db.relationship('User', backref=db.backref('user_uploads', lazy=True))


class Img(db.Model):


    id = db.Column(db.Integer, primary_key = True)
    filename = db.Column(db.String)
    data = db.Column(db.LargeBinary)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User', backref=db.backref('user_images', lazy=True))


        
class Data(db.Model):

    __tablename__ = 'data_files'

    id = db.Column(db.Integer, primary_key = True)
    filename = db.Column(db.String)
    data = db.Column(db.LargeBinary)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User', backref=db.backref('user_data', lazy=True))
    
class Cert(db.Model):

    __tablename__ = 'certificates'

    id = db.Column(db.Integer, primary_key = True)
    filename = db.Column(db.String)
    data = db.Column(db.LargeBinary)
    nazwa = db.Column(db.String)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User', backref=db.backref('user_cert', lazy=True))



app.config['MAIL_SERVER']='smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = 'martakapalka03@gmail.com'
app.config['MAIL_PASSWORD'] = '////////'
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True

mail = Mail(app)


class LoginForm(FlaskForm):
    username = StringField('Nazwa użytkownika', validators=[DataRequired()])
    password = PasswordField('Hasło', validators=[DataRequired()])
    submit = SubmitField('Zaloguj się')


class RegistrationForm(FlaskForm):
    username = StringField('Nazwa użytkownika', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Hasło', validators=[DataRequired()])
    password2 = PasswordField('Powtórz hasło', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Zarejestruj się')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Ta nazwa użytkownika jest już zajęta. Wybierz inną nazwę.')
        
    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('Ten adres email jest już zajęty. Użyj innego adresu email.')

app.config['UPLOAD_EXTENSIONS_WZOR'] = ['.pdf']
@app.route('/login', methods=["GET", "POST"])
def login():
    if current_user.is_authenticated: 
        return redirect(url_for('index')) 
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password')
            return redirect(url_for('login'))
        login_user(user)
        next_page = request.args.get('next')
        if not next_page or url_parse(next_page).netloc != '':
            next_page = url_for('index')
        return redirect(next_page)
    return render_template('login1.html', title='Zaloguj się', form=form)

@app.route('/logout')
def logout():
    logout_user()
    flash('Zostałeś wylogowany')
    return redirect(url_for('index'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Jesteś zarejestrowanym użytkownikiem!')
        return redirect(url_for('login'))
    return render_template('register.html', title='Rejestracja', form=form)


# wyświetlanie listy plików
@app.route('/')
@app.route('/index')
def index():

    if current_user.is_authenticated:
        files = Upload.query.filter_by(user_id=current_user.id).all()
    else: 
        return render_template('logowanie.html', title='Strona główna') 
    return render_template('index.html', files=files, title="Szablony", css='index.css')


#zamiana na polskie litery
def change_letters(szablon_filename):
    new_filename = ''
    for letter in szablon_filename: 
        if letter =="ł":
            new_filename += "l"
        elif letter =="Ł":
            new_filename +="L"
        elif letter =="ą":
            new_filename +="a"
        elif letter =="Ą":
            new_filename +="A"
        elif letter =="ć":
            new_filename +="c"
        elif letter =="Ć":
            new_filename +="C"
        elif letter =="ę":
            new_filename +="e"
        elif letter =="Ę":
            new_filename +="E"
        elif letter =="ó":
            new_filename +="o"
        elif letter =="Ó":
            new_filename +="O"
        elif letter =="ń":
            new_filename +="n"
        elif letter =="Ń":
            new_filename +="N"
        elif letter =="ś":
            new_filename +="s"
        elif letter =="Ś":
            new_filename +="S"
        elif letter =="ż" or letter =="ź":
            new_filename +="z"
        elif letter =="Ż" or letter =="Ź":
            new_filename +="Z"
        else:
            new_filename += letter
    return new_filename

#sprawdzenie czy rozszerzenie się zgadza i zapisanie pliku
def check_extension(szablon_filename, uploaded_file):
    if szablon_filename != '':
        file_ext = os.path.splitext(szablon_filename)[1]
        if file_ext not in app.config['UPLOAD_EXTENSIONS_WZOR']:
            abort(400)
        # zapisanie w bazie danych 
        existing_upload = Upload.query.filter_by(filename=szablon_filename, user_id=current_user.id).first()
        if existing_upload:
            pass
        else:
            upload = Upload(filename = szablon_filename, data=uploaded_file.read(), user_id=current_user.id) 
            db.session.add(upload)
            db.session.commit()


# przesyłanie pliku
@app.route('/', methods=['POST'])
@app.route('/index', methods=['POST'])
def upload_files():
    uploaded_file = request.files['file']
    szablon_filename = uploaded_file.filename
   
    new_filename=change_letters(szablon_filename) 

    new_filename = f'{new_filename[:-4]}_wzor{new_filename[-4:]}'
    szablon_filename = secure_filename(new_filename)

    check_extension(szablon_filename, uploaded_file)

    return redirect(url_for('index'))


# wyświetlenie pliku
@app.route('/szablony/<szablon_filename>', methods=['POST'])
def view_file(szablon_filename):
    file = Upload.query.filter_by(filename=szablon_filename).first()
    if file:
        response = make_response(file.data)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'inline; filename=' + file.filename
        return response
    else:
        return 'Plik o podanej nazwie nie istnieje w bazie danych.'


@app.route("/pdf/<szablon_filename>", methods=['GET'])
def pdf_to_jpg(szablon_filename):

    file = Upload.query.filter_by(filename=szablon_filename, user_id=current_user.id).first()
    pdf_data = BytesIO(file.data)
    doc = fitz.open(stream=pdf_data, filetype="pdf")

    zoom = 4
    mat = fitz.Matrix(zoom, zoom)
    img_filename = f"{szablon_filename[:-9]}.jpg"
    count = len(doc)
    for i in range(count):
        page = doc.load_page(i)
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes()

        existing_upload = Img.query.filter_by(filename=img_filename, user_id=current_user.id).first()
        if existing_upload:
            pass
        else:
            image = Img(filename = img_filename, data=img_data, user_id=current_user.id)
            db.session.add(image)
            db.session.commit()
    doc.close()
    return redirect(url_for('data', img_filename=img_filename))


@app.route('/data/<img_filename>')
def data(img_filename):
    return render_template('data.html', title="Dane", css='index.css')


@app.route('/data/<img_filename>', methods=['POST'])
def send_data(img_filename):
    # przesyłanie pliku z danymi
    uploaded_file = request.files['data_file']
    data_filename = uploaded_file.filename
    # zamiana na polskie znaki
    new_filename = ''
    for letter in data_filename: 
        if letter =="ł":
            new_filename += "l"
        elif letter =="Ł":
            new_filename +="L"
        elif letter =="ą":
            new_filename +="a"
        elif letter =="Ą":
            new_filename +="A"
        elif letter =="ć":
            new_filename +="c"
        elif letter =="Ć":
            new_filename +="C"
        elif letter =="ę":
            new_filename +="e"
        elif letter =="Ę":
            new_filename +="E"
        elif letter =="ó":
            new_filename +="o"
        elif letter =="Ó":
            new_filename +="O"
        elif letter =="ń":
            new_filename +="n"
        elif letter =="Ń":
            new_filename +="N"
        elif letter =="ś":
            new_filename +="s"
        elif letter =="Ś":
            new_filename +="S"
        elif letter =="ż" or letter =="ź":
            new_filename +="z"
        elif letter =="Ż" or letter =="Ź":
            new_filename +="Z"
        else:
            new_filename += letter

    data_filename = secure_filename(new_filename)
    # sprawdzanie czy rozszerzenie się zgadza
    if data_filename != '':
        file_ext = os.path.splitext(data_filename)[1]
        if file_ext not in app.config['UPLOAD_EXTENSIONS_DANE']:
            abort(400)
        # zapisanie 
        filename = secure_filename(uploaded_file.filename)

        csv_data = uploaded_file.read()
        existing_csv = Data.query.filter_by(filename=filename, user_id=current_user.id).first()
        if existing_csv:
            pass
        else:
            csv_file = Data(filename=filename, data=csv_data, user_id=current_user.id)
            db.session.add(csv_file)
            db.session.commit()


    file = Data.query.filter_by(filename=filename).first()
    if file:
        file_data = file.data
        file_data = file_data.decode('utf-8')
        csvfile = io.StringIO(file_data)
        csvreader = csv.reader(csvfile, delimiter=';') 
        for row in csvreader:
            imie = row[2]
            nazwisko = row[3]
            nazwa = row[0] 
            data = row[1] 
            e_mail = row[4]
            podpis = row[5] 

            nazwy = []
            nazwy.append(nazwa)
            image_obj = Img.query.filter_by(filename=img_filename, user_id=current_user.id).first()
            print(type(image_obj))
            image_data = image_obj.data
            
            image = Image.open(BytesIO(image_data))
            filename = f"{imie}_{nazwisko}_{nazwa}.jpg"

            # dopisanie imienia i nazwiska
            dodaj_imie_i_nazwisko = ImageDraw.Draw(image)
            text = f"{imie} {nazwisko}"
            font = ImageFont.truetype("fonts\Geologica-VariableFont_CRSV,SHRP,slnt,wght.ttf", 162)
            
            textwidth, textheight = dodaj_imie_i_nazwisko.textsize(text, font)
            width, height = image.size 
            x=width/2-textwidth/2
            y=1050
            dodaj_imie_i_nazwisko.text((x, y), text, font=font, fill='black')

            # dopisanie nazwy kursu
            dodaj_nazwe = ImageDraw.Draw(image)
            text = f"{nazwa}"
            font = ImageFont.truetype("fonts\Geologica-VariableFont_CRSV,SHRP,slnt,wght.ttf", 90)
            dodaj_nazwe.text((1100, 1600),text, font=font, fill='black')

            # dopisanie daty kursu
            dodaj_date = ImageDraw.Draw(image)
            text = f"{data}"
            font = ImageFont.truetype("fonts\Geologica-VariableFont_CRSV,SHRP,slnt,wght.ttf", 60)
            dodaj_date.text((1980, 1900),text, font=font, fill='black')

            podpis_img = Image.open(podpis)

            new_width = 336
            width, height = podpis_img.size
            aspect_ratio = float(height) / width
            new_height = int(aspect_ratio * new_width)

            podpis_img = podpis_img.resize((new_width,new_height))

            image.paste(podpis_img, (1050,1780))
            image2=image.copy()
            image2= Img(filename = img_filename, data=image_data, user_id=current_user.id)
            db.session.add(image2)
            db.session.commit()

            image = image.convert('RGB')
            filename_certyfikat = f"{filename[:-4]}.pdf"
            
            existing_cert = Cert.query.filter_by(filename=filename_certyfikat, user_id=current_user.id).first()
            if existing_cert:
                continue
            else:
                image_bytes = BytesIO()
                image.save(image_bytes, format='PDF')
                image_bytes = image_bytes.getvalue()

                pdf_cert = Cert(filename = filename_certyfikat, data=image_bytes, user_id=current_user.id, nazwa=nazwa)
                db.session.add(pdf_cert)
                db.session.commit()
                
                # wysyłanie maila 
                cert = Cert.query.filter_by(user_id=current_user.id, filename=filename_certyfikat).first()
                msg = Message(f'Certyfikat {cert.nazwa}', sender='martakapalka03@gmail.com', recipients=[e_mail])
                msg.body = f"Witaj {imie}! Wysyłamy Ci Twój certyfikat. Pozdrawiamy"
                msg.attach(cert.filename, "application/pdf", cert.data)
                mail.send(msg)

    return redirect(url_for('certyfikaty', nazwa=nazwa))

@app.route('/certyfikaty/<nazwa>', methods=['GET'])
def certyfikaty(nazwa):
    if current_user.is_authenticated:
        certificats = Cert.query.filter_by(user_id=current_user.id).all()
    else:
        pass
    return render_template('certyfikaty.html', nazwa=nazwa, certificats=certificats, title="Certyfikaty", css='index.css') 


# wyświetla pojedynczy certyfikat
@app.route('/certyfikaty/<image>', methods=['POST'])
def view_certyfikat(image):
    file = Cert.query.filter_by(filename=image, user_id=current_user.id).first()
    if file:
        response = make_response(file.data)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'inline; filename=' + file.filename
        return response
    else:
        return 'Plik o podanej nazwie nie istnieje.'
    
# pobiera certyfikat
@app.route('/pobierz/<image>', methods=['POST'])
def download_certyfikat(image):
    file = Cert.query.filter_by(filename=image, user_id=current_user.id).first()
    if file:
        response = make_response(file.data)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'attachment; filename=' + file.filename
        return send_file(file.data, download_name=file.filename, as_attachment=True)
    else:
        return 'Plik o podanej nazwie nie istnieje.'

# pobiera wszystkie certyfikaty   
@app.route('/pobierz_wszystko/', methods=['POST'])
def download_all():
    memory_file = io.BytesIO() 
    
    with zipfile.ZipFile(memory_file, 'w') as zipf:
        for file in Cert.query.filter_by(user_id=current_user.id).all():
            if file:
                zipf.writestr(file.filename, file.data)
    
    memory_file.seek(0)  
    
    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name='wszystkie_certyfikaty.zip'
    )


app.app_context().push()
db.create_all()


if __name__ == '__main__':
    app.run(debug=True)
