from PIL import Image, ImageChops, ImageOps
from flask import Flask, request, render_template, redirect, url_for, send_from_directory, flash, session, request, g, json, jsonify
from werkzeug import secure_filename
from model import session as db_session, User, Photo, Vote, Tag, Photo_Tag, Location
import model
import re
import time
import os
# import forms
# import bcrypt

from sqlalchemy import select, func, types, sql, update
from allfunctions import *
from geopy import geocoders

UPLOAD_PHOTO_FOLDER = '/Users/lauren/Desktop/PHOTOS'
ALLOWED_EXTENSIONS = set(['PNG', 'png', 'jpg', 'JPG', 'jpeg','JPEG', 'gif', 'GIF'])

app = Flask(__name__)
app.secret_key = os.environ['SECRET_KEY']
app.config['UPLOAD_PHOTO_FOLDER'] = UPLOAD_PHOTO_FOLDER
app.config.from_object(__name__)

@app.before_request
def load_user_id():
    
    g.user_id = session.get('user_id')
    
    if g.user_id != None:
        g.user = db_session.query(User).filter_by(id=g.user_id)
        g.photos = db_session.query(Photo).filter_by(user_id=g.user_id).all()

def load_photo_id():

    g.photo_id = session.get('id')
    g.photo = db_session.query(Photo).filter_by(id=g.photo_id).one


@app.teardown_request
def shutdown_session(exception = None):
    
    db_session.remove()


@app.route('/')
def home_page():
    
    if g.user_id == None:
        #add error message
        flash("Please sign in first")
    elif g.user_id:
        return redirect(url_for("userpage"))
    return render_template("index.html")


@app.route("/login", methods=["POST"])
def login():
    
    email = request.form['email']
    password = request.form['password']
    
    try:
        u = db_session.query(User).filter_by(email=email, password=password).one()
        
    except:
        flash("Invalid email or password", "error")
        return redirect(url_for("home_page"))

    session['user_id'] = u.id
    return redirect(url_for("userpage"))


@app.route("/signup", methods=['POST'])
def register():
    email = request.form['email']
    username = request.form['username']
    password = request.form['password']
    existing = db_session.query(User).filter_by(email=email).first()
    if existing:
        # FIX FLASH
        flash("Email already in use", "error")
        return redirect(url_for("index"))
    u = User(email=email, password=password, user_name=username)
    print u
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    session['user_id'] = u.id 
    return render_template("index.html")


@app.route("/popular", methods=['GET', 'POST'])
def popular():
    # more recent votes carry more weight, 1/x over time votes' weight goes down dramatically
    sql = """select v.photo_id, p.file_location, p.caption,
    sum( 1 / ( (extract(epoch from now()) - extract(epoch from v.timestamp)) ) * value ) as POPULAR 
    from votes v inner join photos p on p.id = v.photo_id group by p.file_location, v.photo_id, p.caption order by 4 desc;"""
    photos = db_session.execute(sql)
    sql = """select v.photo_id, p.file_location, p.caption,
    sum( 1 / ( (extract(epoch from now()) - extract(epoch from v.timestamp)) ) * value ) as POPULAR 
    from votes v inner join photos p on p.id = v.photo_id group by p.file_location, v.photo_id, p.caption order by 4 desc limit 1;"""
    topPhoto = db_session.execute(sql)
    print topPhoto
    return render_template("popular.html", u=g.user, photos=photos, topPhoto=topPhoto)


@app.route("/map", methods=['GET', 'POST'])
def map():

    return render_template("map.html", u=g.user, photos=g.photos)


@app.route("/vote", methods=['GET', 'POST'])
def vote():
    allphotos=db_session.query(Photo).all()       
    sql = """select distinct v.photo_id
            from votes v where v.give_vote_user_id = %s and v.value > 0;""" % (g.user_id)
    upvotes = [ vote[0] for vote in db_session.execute(sql) ]
    print upvotes
    sql = """select distinct v.photo_id
            from votes v where v.give_vote_user_id = %s and v.value < 0;""" % (g.user_id)
    downvotes = [ vote[0] for vote in db_session.execute(sql) ]

    
    if request.form:

        vote = request.form['vote']
        photoid = request.form['photoid']
        photoowner = request.form['photoowner']

        v = db_session.query(Vote).filter_by(give_vote_user_id=g.user_id, photo_id=photoid).first()
        if not v:
            v = Vote(give_vote_user_id=g.user_id, photo_id=photoid, receive_vote_user_id=photoowner)
            db_session.add(v)

        p = db_session.query(Photo).filter_by(id=photoid).one()

        if vote == "upvote":
            v.value = 1
            p.up_vote = Photo.up_vote + 1
        elif vote == "downvote":
            v.value = -1
            p.down_vote = Photo.down_vote + 1        
        
        db_session.commit()
        sql = """select distinct v.photo_id
        from votes v where v.give_vote_user_id = %s and v.value > 0;""" % (g.user_id)
        upvotes = [ vote[0] for vote in db_session.execute(sql) ]
        sql = """select distinct v.photo_id
        from votes v where v.give_vote_user_id = %s and v.value < 0;""" % (g.user_id)
        downvotes = [ vote[0] for vote in db_session.execute(sql) ]

        return render_template("_vote.html", u=g.user, photos=allphotos, upvotes=upvotes, downvotes=downvotes)

    return render_template("vote.html", u=g.user, photos=allphotos, upvotes=upvotes, downvotes=downvotes)


@app.route("/userpage")
def userpage():

    if not g.user_id:
        print "FLASH TEST"
        flash("Please log in", "warning")
        return redirect(url_for("/"))

    return render_template("userpage.html", u=g.user, photos=g.photos)


@app.route("/logout")
def logout():

    del session['user_id']
    return render_template("index.html")


@app.route('/upload', methods=['GET', 'POST'])
# this function corresponds to the jinja {{url_for("uploadfile")}} ACTION in upload.html
def uploadfile():

    if request.method == 'POST':
        file = request.files['file']

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            photo_location = "uploads/"+filename
            photo_file_path = os.path.join(app.config['UPLOAD_PHOTO_FOLDER'], filename)
            file.save(photo_file_path)
            
            thumbnail_file_path = os.path.splitext(photo_file_path)[0] + ".thumbnail"
            create_thumbnail(filename, photo_file_path, thumbnail_file_path)
            thumbnail_location = "uploads/"+ os.path.splitext(filename)[0] + ".thumbnail"
            image = Image.open(photo_file_path)
            exif_data = get_exif_data(image)
            latlon = get_lat_lon(exif_data)

            l = str(latlon)
            latitude = lat(l)
            longitude = lon(l)
            timestamp = get_time(exif_data)

            if timestamp != None:
                timestamp = datetime.strptime(str(timestamp), "%Y:%m:%d %H:%M:%S")

            caption = request.form['caption']

            p = Photo(file_location=photo_location, caption=caption, latitude=latitude, longitude=longitude, timestamp=timestamp, user_id=g.user_id, thumbnail=thumbnail_location)

            db_session.add(p)
            db_session.commit()
            db_session.refresh(p)

            if latitude == None:
                # photo_id is a key and p.id is a value and session is a dict
                print "SESSION"
                session['photo_id'] = p.id
                return redirect(url_for('addlocation', photo_id=p.id))

            user = db_session.query(User).filter_by(id=g.user_id).one()
            # create a template that shows the view of an uploaded photo and then the user's other photos
            return redirect(url_for('userpage'))      
    
    return render_template("upload.html")


@app.route('/addlocation', methods=['POST', 'GET'])
def addlocation():
    if request.method == 'POST':
        
        #.get using the key photo_id to get the value which is the photo_id
        photo_id = session.get('photo_id')
        city = request.form['city']

        goo = geocoders.GoogleV3()
        geocodes = goo.geocode(city, exactly_one=False)
        l2 = str(geocodes)
        latitude = lat2(l2)
        longitude = lon2(l2)
        # query by photo_id and update latlng
        db_session.query(Photo).filter_by(id=photo_id).update({"latitude": latitude, "longitude": longitude})
        db_session.commit()
        db_session.flush()
        del session['photo_id']
   
        return redirect(url_for('userpage')) 
    return render_template("upload2.html")

@app.route('/photosearch', methods=['POST', 'GET'])
def photosearch():
    if request.method == 'POST':
        print "POST"
        search = request.form['searchText']
        print search
        goo = geocoders.GoogleV3()
        print "GOO:", goo
        geocodes = goo.geocode(search, exactly_one=False)
        l2 = str(geocodes)
        latitude = lat2(l2)
        longitude = lon2(l2)
        
        return jsonify(latitude=latitude, longitude=longitude)


@app.route('/uploads/<filename>')
def uploaded_file(filename):

    # create a template for this
    return send_from_directory(app.config['UPLOAD_PHOTO_FOLDER'],
                               filename)


if __name__ == '__main__':
    app.run(debug=True)

    