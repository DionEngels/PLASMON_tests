%% setup
number_x = 20;
number_y = 10;
n_objects = number_x*number_y; %# objects

SNRs = [0.25, 0.5,  0.75, 1:1:10, 15, 20 30 40 60 80 100];

pixel_spacing_x = 20;
pixel_spacing_y = pixel_spacing_x;

mic_pixels_x = (number_x+1)*pixel_spacing_x; %# pixels
mic_pixels_y = (number_y+1)*pixel_spacing_y; %# pixels

mic_pixelsize = 200;

pos_x = [pixel_spacing_x:pixel_spacing_x:number_x*pixel_spacing_x]*mic_pixelsize;
pos_y = [pixel_spacing_y:pixel_spacing_y:number_y*pixel_spacing_y]*mic_pixelsize;

pos_x = (pos_x - 0.5*mic_pixelsize)/1e9; % pixel adjust
pos_y = (pos_y - 0.5*mic_pixelsize)/1e9; % pixel adjust

n_frames = 1000;
%% load in data
% Use "import data"
% Import as Numeric Matrix

%% fit checker setup
columns_not_fitted = [1 2 3];
x_column = 2; %what column has x-pos in the return data
y_column = 3; %what column has y-pos in the return data
n_fits_per_frame = (number_x-size(columns_not_fitted,2))*number_y;
i_fit = 1; % row index

%% fit checker %% clear test
clear res_precision res_accuracy res_mean res_precision_imageJ
for i=1:number_x
    for j=1:number_y
    if ismember(i, columns_not_fitted)
        continue
    end
    fit_x = data((i-1-size(columns_not_fitted,2))*number_y+j:n_fits_per_frame:n_frames*n_fits_per_frame,x_column);%ones(1,n_frames)*59.5+(rand(1,n_frames)-0.5);%data((i-1)*number_y+j:n_fits_per_frame:n_frames*n_fits_per_frame,x_column);
    fit_y = data((i-1-size(columns_not_fitted,2))*number_y+j:n_fits_per_frame:n_frames*n_fits_per_frame,y_column);%ones(1,n_frames)*19.5+(rand(1,n_frames)-0.5);%data((i-1)*number_y+j:n_fits_per_frame:n_frames*n_fits_per_frame,y_column);
    fit_uncertainty = data((i-1-size(columns_not_fitted,2))*number_y+j:n_fits_per_frame:n_frames*n_fits_per_frame,9); % 8 for MLE, 9 for LS
    % convert all to m
    fit_x = fit_x / 1e9;
    fit_y = fit_y / 1e9;
    fit_uncertainty = fit_uncertainty / 1e9;
    res_precision_imageJ(i,j) = mean(fit_uncertainty);
    fit_x_mean = mean(fit_x);
    fit_y_mean = mean(fit_y);
    sigma_x = sum((fit_x - fit_x_mean).^2)/(size(fit_x,1)-1);
    sigma_y = sum((fit_y - fit_y_mean).^2)/(size(fit_y,1)-1);
    res_precision(i,j) = sqrt(sigma_x^2 + sigma_y^2);
    res_accuracy(i,j) = sqrt(sum(([pos_x(i) pos_y(j)] - [fit_x_mean fit_y_mean]).^2));
   % dif = 
    end
end

% convert all back to nm

res_precision_imageJ = res_precision_imageJ*1e9;
res_precision = res_precision*1e9;
res_accuracy = res_accuracy*1e9;

res_precision_imageJ = mean(res_precision_imageJ,2);
res_precision = mean(res_precision,2);
res_accuracy = mean(res_accuracy,2);
%% clear test
%clear res_precision res_accuracy res_mean