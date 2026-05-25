////////////////////////////////
// Setup
////////////////////////////////

// Gulp and package
import { src, dest, parallel, series, task, watch } from 'gulp';
import pjson from './package.json' with {type: 'json'};

// Plugins
import autoprefixer from 'autoprefixer';
import browserSyncLib from 'browser-sync';
import concat from 'gulp-concat';
import tildeImporter from 'node-sass-tilde-importer';
import cssnano from 'cssnano';
import pixrem from 'pixrem';
import plumber from 'gulp-plumber';
import postcss from 'gulp-postcss';
import rename from 'gulp-rename';
import gulpSass from 'gulp-sass';
import * as dartSass from 'sass';
import gulUglifyES from 'gulp-uglify-es';
import { spawn } from 'node:child_process';
import rtlcss from "gulp-rtlcss";
import sourcemaps from "gulp-sourcemaps";
import npmdist from 'gulp-npm-dist';
import pluginFile from './plugins.config.js';

const browserSync = browserSyncLib.create();
const reload = browserSync.reload;
const sass = gulpSass(dartSass);
const uglify = gulUglifyES.default;



// Relative paths function
function pathsConfig() {
  const appName = `./${pjson.name}`;
  const vendorsRoot = 'node_modules';

  return {
    app: appName,
    templates: `${appName}/templates/`,
    css: `${appName}/static/css/`,
    scss: `${appName}/static/scss/`,
    fonts: `${appName}/static/fonts/`,
    images: `${appName}/static/images/`,
    js: `${appName}/static/js/`,
    plugins: `${appName}/static/plugins/`,
  };
}

const paths = pathsConfig();

////////////////////////////////
// Tasks
////////////////////////////////

const processCss = [
   autoprefixer(), // adds vendor prefixes
   pixrem(), // add fallbacks for rem units
];

const minifyCss = [
   cssnano({ preset: 'default' }), // minify result
];

// Copying Third Party Plugins Assets
const plugins = function () {
    const out = paths.plugins ;

    pluginFile.forEach(({name, vendorsJS, vendorsCSS, vendorFonts, assets, fonts, font, media, img, webfonts}) => {

        const handleError = (label, files) => (err) => {
            const shortMsg = err.message.split('\n')[0];
            console.error(`\n${label} - ${shortMsg}`);
            throw new Error(`${label} failed`);
        };

        if (vendorsJS) {
            src(vendorsJS)
                .on('error', handleError('vendorsJS'))
                .pipe(concat('vendors.js'))
                .pipe(dest(paths.js))
                .pipe(plumber()) // Checks for errors
                .pipe(uglify()) // Minifies the js
                .pipe(rename({ suffix: '.min' }))
                .pipe(dest(paths.js));
        }

        if (vendorsCSS) {
            src(vendorsCSS)
                .pipe(concat("vendors.min.css"))
                .on('error', handleError('vendorsCSS'))
                .pipe(dest(paths.css));
        }

        if (vendorFonts) {
            src(vendorFonts)
                .on('error', handleError('vendorFonts'))
                .pipe(dest(paths.css + "/fonts/"));
        }

        if (assets) {
            src(assets)
                .on('error', handleError('assets'))
                .pipe(dest(`${out}${name}/`));
        }

        if (img) {
            src(img)
                .on('error', handleError('img'))
                .pipe(dest(`${out}${name}/img/`));
        }

        if (media) {
            src(media)
                .on('error', handleError('media'))
                .pipe(dest(`${out}${name}/`));
        }

        if (fonts) {
            src(fonts)
                .on('error', handleError('fonts'))
                .pipe(dest(`${out}${name}/fonts/`));
        }

        if (font) {
            src(font)
                .on('error', handleError('font'))
                .pipe(dest(`${out}${name}/font/`));
        }

        if (webfonts) {
            src(webfonts)
                .on('error', handleError('webfonts'))
                .pipe(dest(`${out}${name}/webfonts/`));
        }
    });

    return Promise.resolve();
};

// Styles autoprefixing and minification
function styles() {

//  src(`${paths.scss}/app.scss`)
//        .pipe(
//            sass({
//                importer: tildeImporter,
//                includePaths: [paths.scss],
//            }).on('error', sass.logError),
//        )
//        .pipe(plumber()) // Checks for errors
//        .pipe(postcss(processCss))
//        .pipe(rename({suffix: '-rtl'}))
//        .pipe(rtlcss())
//        .pipe(dest(paths.css))
//        .pipe(rename({suffix: '.min'}))
//        .pipe(postcss(minifyCss)) // Minifies the result
//        .pipe(dest(paths.css));

  return src(`${paths.scss}/**/*.scss`)
    .pipe(sourcemaps.init())
    .pipe(
      sass({
        importer: tildeImporter,
        includePaths: [paths.scss],
      }).on('error', sass.logError),
    )
    .pipe(plumber()) // Checks for errors
    .pipe(postcss(processCss))
    .pipe(dest(paths.css))
    .pipe(rename({ suffix: '.min' }))
    .pipe(postcss(minifyCss)) // Minifies the result
    .pipe(sourcemaps.write('.')) //generates .map
    .pipe(dest(paths.css));
}


// Watch
function watchPaths() {
  watch(`${paths.scss}/**/*.scss`, styles);
}

// Generate all assets
const build = parallel(styles, plugins);

// Set up dev environment
const dev = parallel(watchPaths);

task('default', series(build, dev));
task('build', build);
task('dev', dev);
